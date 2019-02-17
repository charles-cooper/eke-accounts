import web3
import time
import argparse
import sys, os
import sqlite3, json
import asyncio, aiohttp

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

async def _get_block_async(session, uri, blknum) :
    req = { "method":"eth_getBlockByNumber",
            "params":[w3.toHex(blknum),True],
            "id":1,
            "jsonrpc":"2.0"
            }
    async with session.post(uri, json=req) as res :
        txt = await res.text()
        res = json.loads(txt)
        if 'error' in res :
            raise ValueError(res['error'])
        else :
            return res['result']

def getBlocksBatched(session, uri, loop, fromBlock, toBlock) :
    return loop.run_until_complete(
            asyncio.gather(*[_get_block_async(session, uri, blknum)
                for blknum in range(fromBlock, toBlock + 1)]))

if __name__ == '__main__' :

    parser = argparse.ArgumentParser()
    parser.add_argument('--web3-provider-uri', help='Web3.py provider uri (same format as WEB3_PROVIDER_URI')
    args = parser.parse_args()

    initdb()

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

    loop = asyncio.get_event_loop()

    session = aiohttp.ClientSession(raise_for_status=True)

    latest = w3.eth.getBlock('latest').number
    current_block = 0
    while True :
        if current_block < latest :
            start = time.time()
            CHUNK_SIZE = 100
            next_block = min(current_block + CHUNK_SIZE, latest)
            uri = args.web3_provider_uri or os.environ['WEB3_PROVIDER_URI']
            print('ENTER 1')
            blks = getBlocksBatched(session, uri, loop, current_block, next_block)
            print('ENTER 2')
            print(len(blks))
            print(f'cur {next_block}')
            end = time.time()
            print(f'{end - start}s')
            current_block = next_block
        else :
            time.sleep(1)
