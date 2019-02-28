import web3
import time
import argparse
import sys, os
import sqlite3, json
import hashlib
import asyncio
from aiohttp import web
import logging

def initdb(dbpath='shorthash.db') :
    c = sqlite3.connect(dbpath, isolation_level=None)

    # create schema
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
    prefix text,
    suffix text,
    shorthash text primary key,
    address text)''') # address is stored checksummed and hex encoded
    c.execute('''create index if not exists accounts_prefix_idx
        on accounts(prefix)''')
    c.execute('''create index if not exists accounts_address_idx_
        on accounts(address)''')

    c.execute('''CREATE TABLE IF NOT EXISTS unusable_shorthashes (
        shorthash text primary key)''')

    c.execute('''CREATE TABLE IF NOT EXISTS current_block (block int)''')
    c.execute('begin')
    rs = list(c.execute('select * from current_block'))
    if not rs :
        c.execute('insert into current_block values (0);')
        c.commit()
    else :
        c.rollback()
    return c

with open('bip0039-english.txt') as f :
    WORDS = [ word.strip() for word in f.readlines() ]

def address_to_words(addr) :
    bs = web3._utils.encoding.decode_hex(addr)
    chksm = hashlib.sha256(bs).digest()[:2]
    addrint = int.from_bytes(bs + chksm, byteorder='little')
    ret = []
    for i in range(0, 16) :
        ret.append(WORDS[addrint & ((1<<11) - 1)])
        addrint >>= 11
    return ret

def process_block(c, blk) :
    txns = blk.transactions
    addrs = [] # web3 returns checksummed addresses
    for txn in txns :
        if 'from' in txn and txn['from'] :
            addrs.append(txn['from'])
        if 'to' in txn and txn['to'] :
            addrs.append(txn['to'])
    merge_addresses(c, addrs)

def process_genesis(c, genesis) :
    addrs = []
    for acct in genesis['accounts'] :
        if 'balance' in genesis['accounts'][acct] :
            addrs.append(acct)
    addrs = [ w3.toChecksumAddress(addr) for addr in addrs ]
    merge_addresses(c, addrs)
    print('Genesis processed')

# For each of words1 and words2, find the shortest prefix that doesn't
# begin the other word.
def resolve_conflict(words1, words2) :
    assert words1 != words2
    ret1 = []
    ret2 = []
    ret3 = []
    for w1, w2 in zip(words1, words2) :
        ret1.append(w1)
        ret2.append(w2)
        if w1 != w2 :
            break
        ret3.append(w1)
    assert ret1 != ret2
    return ret1, ret2, ret3

def _prefix(words) :
    return ' '.join((words[0],words[1]))

def _suffix(words) :
    return ' '.join((words[-2],words[-1]))

def _possible_prefixes(words) :
    # starting at 2- word prefix
    return [ ' '.join(words[0:i+1]) for i in range(1,len(words)) ]

# Merge in addresses, breaking shorthash collisions when found
# Slow/naive implementation, not batched.
def merge_addresses(c, addrs) :
    for addr in addrs :
        # print(addr)
        words = address_to_words(addr)
        prefix = _prefix(words)
        suffix = _suffix(words)
        possible_prefixes = _possible_prefixes(words)
        # print(possible_prefixes)
        exists = len(list(c.execute(
            f'select * from accounts where address = ?', (addr,))))
        if exists :
            continue
        else :
            resultset = list(c.execute(
                f'''select *
                from accounts
                where shorthash in
                    ({','.join(['?' for _ in possible_prefixes])})''',
                possible_prefixes))

            # INVARIANT at most one shorthash can be a prefix of this address.
            # otherwise a merge would have already broken the collision.
            assert len(resultset) <= 1, (addr, possible_prefixes)

            if not resultset :
                c.execute('begin')
                unusable_prefixes = [x[0] for x in c.execute(
                    f'''select *
                    from unusable_shorthashes
                    where shorthash in
                        ({','.join(['?' for _ in possible_prefixes])})''',
                    possible_prefixes)]
                available_shorthashes = \
                        [ p for p in possible_prefixes
                                if p not in unusable_prefixes ]
                assert len(available_shorthashes) > 0, addr
                shorthash = available_shorthashes[0]
                # print(addr, unusable_prefixes, available_shorthashes, shorthash)
                c.execute(f'insert into accounts VALUES (?,?,?,?)',
                        (prefix, suffix, shorthash, addr))
                c.execute('commit')
            else :
                (ex_prefix, ex_suffix, _, ex_addr) = resultset[0]

                ex_words = address_to_words(ex_addr)

                shorthash, ex_shorthash, unusable = \
                        resolve_conflict(words, ex_words)

                unusable_shorthashes = _possible_prefixes(unusable)
                shorthash = ' '.join(shorthash)
                ex_shorthash = ' '.join(ex_shorthash)

                c.execute('begin')

                # upsert new used shorthashes
                c.execute(f'''delete
                    from unusable_shorthashes
                    where shorthash in
                        ({','.join(['?' for _ in unusable_shorthashes])})''',
                        unusable_shorthashes)
                c.execute(f'''insert
                    into unusable_shorthashes (shorthash) VALUES
                        {','.join(['(?)' for _ in unusable_shorthashes])}''',
                        unusable_shorthashes)

                # upsert the old account with new shorthash
                c.execute(f'delete from accounts where address = ?', (ex_addr,))
                c.execute(f'insert into accounts VALUES (?,?,?,?)',
                        (ex_prefix, ex_suffix, ex_shorthash, ex_addr))
                # insert the new account
                c.execute(f'insert into accounts VALUES (?,?,?,?)',
                        (prefix, suffix, shorthash, addr))
                c.execute(f'commit')

async def poll_blocks() :
    global current_block
    while True :
        latest = w3.eth.getBlock('latest').number
        # (don't handle reorgs)
        if current_block < latest :
            # always a block behind
            blk = w3.eth.getBlock(current_block, full_transactions=True)
            process_block(c, blk)
            current_block += 1
            c.execute('update current_block set block = ?', (current_block,))
            await asyncio.sleep(0.00001) # give other coros chance to grab execution
        else :
            await asyncio.sleep(1)

async def get_current_block(req) :
    global current_block
    return web.json_response({'current_block': current_block})

def parse_resultset(resultset) :
    ret = [ {
                'prefix': prefix,
                'suffix': suffix,
                'shorthash': shorthash,
                'address': address }
            for (prefix, suffix, shorthash, address) in resultset ]
    return ret

async def get_accounts_by_prefix(req) :
    q = req.rel_url.query
    prefix = q.get('prefix')
    # print(prefix)
    if not prefix :
        raise web.HTTPBadRequest(reason='param \'prefix\' required')
    dat = parse_resultset(list(c.execute(
        'select * from accounts where prefix = ?', (prefix,))))
    return web.json_response(dat)

async def get_account_by_address(req) :
    q = req.rel_url.query
    addr = q.get('address')
    if not addr :
        raise web.HTTPBadRequest(reason='param \'address\' required')
    addr = w3.toChecksumAddress(addr)
    # print(prefix)
    dat = parse_resultset(list(c.execute(
        'select * from accounts where address = ?', (addr,))))
    return web.json_response(dat[0])

async def run_server() :
    app = web.Application()
    app.add_routes([
        web.get('/current-block', get_current_block),
        # merge these and switch on query param?
        web.get('/accounts-by-prefix', get_accounts_by_prefix),
        web.get('/account-by-address', get_account_by_address),
        ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

if __name__ == '__main__' :

    parser = argparse.ArgumentParser()
    parser.add_argument('--web3-provider-uri', help='Web3.py provider uri (same format as WEB3_PROVIDER_URI')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    if args.test :
        try :
            os.remove('test.db')
        except FileNotFoundError :
            pass
        c = initdb('test.db')
        addresses = [
                '0xb9791670d62591222bb999ae9c81485c7c91eb41',
                '0xb9791670d62591222bb999ae9c81485c7c91eb42',
                '0x0000000083178E9873ce992f73915EEfa3A27aC5',
                '0x00000000742A16c2ccFdf3A6FDe782E6e95b4120',
                '0x0000000000000000000000000000000000000000',
                '0x0000000000000000000000000000000000000001',
                '0x0000000103026f36d9f2BA6468d2816Cd5Dce83a',
                '0x0000000000000000000000000000000000000123',
                '0x0000000000000000000000000000000000000027',
                '0x0000000000000000000000000000000000001337',
                '0x00000000202cb962ac59075B964b07152d234B70',
                '0x00000000D48105B0110dafb0D131FaDDE9AAF59b',
                '0x00000000Be9b6073d2fD2516d0162B768830A2c8',
                '0x00000000Ae6D2Dd2417733BfA7DeDE6AA10efB58',
                '0x000000006766DC158D9D167aeed0D00De5CF1743',
                ]
        merge_addresses(c, addresses)
        for x in c.execute('select * from accounts') :
            print(x)
        sys.exit(0)
    else :
        c = initdb()

    if args.web3_provider_uri :
        p = web3.providers.auto.load_provider_from_uri(args.web3_provider_uri)
        w3 = web3.Web3(p)
    else :
        w3 = web3.Web3()

    if False : # w3.eth.syncing :
        sys.stderr.write('Connected, node syncing...\n')
        while w3.eth.syncing :
            time.sleep(1)
        sys.stderr.write('Synced!\n')
    else :
        sys.stderr.write('Connected.\n')

    loop = asyncio.get_event_loop()
    current_block = list(c.execute('select * from current_block'))[0][0]
    print(current_block)

    if current_block == 0 :
        with open('foundation.json') as f :
            genesis = json.loads(f.read())
        process_genesis(c, genesis)

    # logging.getLogger('aiohttp.web').setLevel('DEBUG')
    # logging.getLogger('aiohttp.server').setLevel('DEBUG')
    # logging.getLogger('aiohttp.internal').setLevel('DEBUG')
    # logging.getLogger('aiohttp.access').setLevel('DEBUG')

    # TODO exception handling
    loop.run_until_complete(asyncio.gather(
        poll_blocks(),
        run_server()))
