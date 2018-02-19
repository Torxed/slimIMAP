SlimIMAP
========

A Simple and Slim IMAP server aiming for a minimalistic and simple design.

Installation
============

`git clone` this repo, or if you're on Arch Linux:

    # pacaur -S slimIMAP

Configuration
=============

**TODO:** Many of these options are not in use, they're taken from [slimSMTP](https://github.com/Torxed/slimSMTP) which shares similar features.

The basic idea is that you simply modify `configuration.py` in the code the dictionary itself or under `/etc/slimIMAP/`.<br>
This consist of a few settings which I'll try to explain here:

 * domains         - A sub-dictionary to enable support for multiple domain configurations.
 * users           - Now, this is **NOT** email address, it's the accounts we can authenticate for external mail deliveries.
                     The fields which needs to be defined for each user are `password` which, will be required if the sender tries to send external emails.
                     `storage` which is the storage class slimIMAP will use to call `.store(from, to, message)` on in order to store the incomming email.
 * mailboxes       - For now, these are key, value pairs where the key is the full email address and the value is the username it belongs to.
 * filepermissions - Unless `owner=...` is specified in the `users` configuration, these filepermissions will be used. (note: `user` definitions override `filepermissions`!)
 * ssl             - Contains certificate and version information and a flag to enforce SSL for _all_ sockets and mail-deliveries.
 * postgresql      - Credentials for the database backend (if opted in for it) [TODO: bring back PostgreSQL mailbox delivery options]
 * pidfile         - It is what it is, it's the pid file

 How to run
==========

It shouldn't be more to it than to run:

    # python slimIMAP.py

Changelog
=========

### 0.0.1

 * Very crude basic functionality
 * Supports authenticating (PLAIN method only atm)
 * Partially supports SELECT, LIST, UNSUBSCRIBE, LSUB, NOOP, CREATE