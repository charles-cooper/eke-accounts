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
    addrint = int.from_bytes(bs + chksm, byteorder='big')
    ret = []
    for i in range(0, 16) :
        ret.append(WORDS[addrint & 2047])
        addrint >>= 11
    return ret

def process_block(c, blk) :
    txns = blk.transactions
    addrs = []
    for txn in txns :
        addrs += [ txn['from'], txn['to'] ]
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

# Merge in addresses, breaking shorthash collisions when found
# Slow/naive implementation, not batched.
def merge_addresses(c, addrs) :
    for addr in addrs :
        words = address_to_words(addr)
        possible_shorthashes = [ ' '.join(
        prefix = ' '.join((w[0],w[1]))
        suffix = ' '.join((w[-2],w[-1]))
        exists = len(c.executemany(
            f'select * from addresses where address = (?)'))
        if exists :
            continue
        else :
            resultset = list(c.execute(
                f'select * from addresses where shorthash in ({",".join(["?" for _ in words])})'))
            # INVARIANT at most one shorthash can be a prefix of this address.
            # otherwise a merge would have already broken the collision.
            assert len(resultset) <= 1
            if not resultset :
                c.execute(f'insert into addresses ?', address) # other cols
            else :
                new_words1, new_words2 = resolve_conflict(words1, words2)
                c.execute('begin')
                c.execute(f'delete from addresses where address = ?', existing_address)
                c.execute(f'insert into addresses ?', new_address1) # other cols
                c.execute(f'insert into addresses ?', new_address2) # other cols
                c.execute(f'commit')

if __name__ == '__main__' :

    parser = argparse.ArgumentParser()
    parser.add_argument('--web3-provider-uri', help='Web3.py provider uri (same format as WEB3_PROVIDER_URI')
    args = parser.parse_args()

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

    current_block = list(c.execute('select * from current_block'))[0][0]
    current_block = 1000000
    print(current_block)
    while True :
        latest = w3.eth.getBlock('latest').number
        if current_block < latest :
            blk = w3.eth.getBlock(current_block, full_transactions=True)
            process_block(c, blk)
            current_block += 1
        else :
            time.sleep(1)
