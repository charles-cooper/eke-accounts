## eke-accounts

This repository is the result of conversations with @wwithiam at
ETHDenver 2019. The idea is that, while there are near-infinite unique
Ethereum addresses (2^20), the number of addresses which have been
interacted with is much smaller (70 million or so as of time of
writing). Using a 2048-word wordlist, we can represent all 'touched'
addresses with just 2-3 words apiece. This address calculates the
shortest unique prefix for each seen address and stores it in a database
so one can look up the full address from its 'shorthash'.
