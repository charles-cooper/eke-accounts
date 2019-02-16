import web3
import argparse

if __name__ == '__main__' :
    if args.web3_provider_uri :
        p = web3.providers.auto.load_provider_from_uri(args.web3_provider_uri)
        w3 = Web3(p)
    else :
        w3 = Web3()

