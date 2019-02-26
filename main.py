import web3
import time
import argparse
import sys, os
import sqlite3, json
import hashlib
# import asyncio, aiohttp

def initdb() :
    c = sqlite3.connect('shorthash.db', isolation_level=None)
    # create schema
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
    prefix text,
    suffix text,
    shorthash text primary key,
    address text)''') # address is stored checksummed and hex encoded
    c.execute('''create index if not exists accounts_prefix_idx
    on accounts(prefix)''')
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
    addrs = []
    for txn in txns :
        if 'from' in txn and txn['from'] :
            addrs.append(txn['from'])
        if 'to' in txn and txn['to'] :
            addrs.append(txn['to'])
    merge_addresses(c, addrs)

# For each of words1 and words2, find the shortest prefix that doesn't
# begin the other word.
def resolve_conflict(words1, words2) :
    assert words1 != words2
    ret1 = []
    ret2 = []
    for w1, w2 in zip(words1, words2) :
        ret1.append(w1)
        ret2.append(w2)
        if w1 != w2 :
            break
    assert ret1 != ret2
    return ret1, ret2

# Merge in addresses, breaking shorthash collisions when found
# Slow/naive implementation, not batched.
def merge_addresses(c, addrs) :
    for addr in addrs :
        words = address_to_words(addr)
        prefix = ' '.join((words[0],words[1]))
        suffix = ' '.join((words[-2],words[-1]))
        possible_prefixes = [ # starting at 2- word prefix
                ' '.join(words[0:i+1])
                for i in range(1,len(words)) ]
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
            assert len(resultset) <= 1
            if not resultset :
                c.execute(f'insert into accounts VALUES (?,?,?,?)',
                        (prefix, suffix, prefix, addr))
            else :
                (ex_prefix, ex_suffix, _, ex_addr) = resultset[0]
                ex_words = address_to_words(ex_addr)
                shorthash, ex_shorthash = resolve_conflict(words, ex_words)
                shorthash = ' '.join(shorthash)
                ex_shorthash = ' '.join(ex_shorthash)
                c.execute('begin')
                c.execute(f'delete from accounts where address = ?', (ex_addr,))
                c.execute(f'insert into accounts VALUES (?,?,?,?)',
                        (ex_prefix, ex_suffix, ex_shorthash, ex_addr))
                c.execute(f'insert into accounts VALUES (?,?,?,?)',
                        (prefix, suffix, shorthash, addr))
                c.execute(f'commit')

if __name__ == '__main__' :

    parser = argparse.ArgumentParser()
    parser.add_argument('--web3-provider-uri', help='Web3.py provider uri (same format as WEB3_PROVIDER_URI')
    args = parser.parse_args()

    c = initdb()

    TEST = False
    if TEST :
        addresses = [
                '0xb9791670d62591222bb999ae9c81485c7c91eb41',
                '0xb9791670d62591222bb999ae9c81485c7c91eb42',
                ]
        merge_addresses(c, addresses)
        for x in c.execute('select * from accounts') :
            print(x)
        sys.exit(0)

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

    current_block = list(c.execute('select * from current_block'))[0][0]
    # current_block = 1000000
    print(current_block)
    while True :
        latest = w3.eth.getBlock('latest').number
        # (don't handle reorgs)
        if current_block < latest :
            # always a block behind
            blk = w3.eth.getBlock(current_block, full_transactions=True)
            process_block(c, blk)
            current_block += 1
            c.execute('update current_block set block = ?', (current_block,))
        else :
            time.sleep(1)
