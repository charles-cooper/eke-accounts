print('ENTER 0')

import web3
import time
import argparse
import sys, os
import sqlite3, json
# import asyncio, aiohttp

print('ENTER 1')

def initdb() :
    c = sqlite3.connect('shorthash.db', isolation_level=None)
    # create schema
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
    prefix text,
    shorthash text primary key,
    address text)''') # address is stored checksummed and hex encoded
    c.execute('''create index if not exists accounts_prefix_idx
    on accounts(prefix)''')
    c.execute('''CREATE TABLE IF NOT EXISTS current_block (block int)''')
    c.execute('begin')
    rs = c.execute('select * from current_block')
    if not rs :
        c.execute('insert into current_block values (0);')
        c.commit()
    else :
        c.rollback()
    return c

print('ENTER 2')

with open('bip0039-english.txt') as f :
    WORDS = [ word.strip() for word in f.read().split('\n') ]

print(WORDS)

print('ENTER 3')

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

    if w3.eth.syncing :
        sys.stderr.write('Connected, node syncing...\n')
        while w3.eth.syncing :
            time.sleep(1)
        sys.stderr.write('Synced!\n')
    else :
        sys.stderr.write('Connected.\n')

    # loop = asyncio.get_event_loop()
    # session = aiohttp.ClientSession(raise_for_status=True)

    current_block = 0
    while True :
        print('ENTER')
        latest = w3.eth.getBlock('latest').number
        if current_block < latest :
            w3.eth.getBlock(current_block)
            current_block += 1
        else :
            time.sleep(1)
