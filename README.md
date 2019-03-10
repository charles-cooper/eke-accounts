## eke-accounts

This repository is a proof-of-concept implementation of conversations
with @wwithiam at ETHDenver 2019. The idea is that, while there are
near-infinite unique Ethereum addresses (2^20), the number of addresses
which have been interacted with is much smaller (70 million or so as of
time of writing). Using a 2048-word wordlist, we can represent all
'touched' addresses with just 2-3 words apiece. This codebase calculates
the shortest unique prefix for each seen address and stores it in a
database so one can look up the full address from its 'shorthash'. It
also implements a simple HTTP server to help query the database
remotely.

As a service to the community, a server running this software is hosted
at shorthash.coopertech.co. Example usage:
```bash
$ curl shorthash.coopertech.co/current-block
{"current_block": 8137}
$ curl shorthash.coopertech.co/account-by-address/0x631030A5B27B07288a45696F189E1114f12A81c0
{"prefix": "arrest scare", "suffix": "toward thing", "shorthash": "arrest scare family", "address": "0x631030A5B27B07288a45696F189E1114f12A81c0"}
# Use the 'validate_checksum' query param to ensure the address is properly checksummed.
$ curl http://shorthash.coopertech.co/account-by-address/0x631030a5b27b07288a45696f189e1114f12a81c0?validate_checksum
400: invalid checksummed address
$ curl shorthash.coopertech.co/accounts-by-prefix?prefix=arrest%20scare
[{"prefix": "arrest scare", "suffix": "pony emerge", "shorthash": "arrest scare motion", "address": "0x6310B020fD98044957995092090F17F04e52cdfD"}, {"prefix": "arrest scare", "suffix": "toward thing", "shorthash": "arrest scare family", "address": "0x631030A5B27B07288a45696F189E1114f12A81c0"}]
```
