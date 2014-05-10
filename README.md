Greylisting service for Postfix
===============================

This is a re-implementation of the ``greylist.pl`` shipping with
postfix. ``greylist.py`` has some advantages over ``greylist.pl``:

1. It uses sqlite, so concurrency is possible
2. It has limiting options, to prevent the database from eating all the
   diskspace.

   **Note:** Using this (it is enabled by default!) is a possible attack
   vector. If an attacker manages to fill (and keep it filled) the whole
   greylisting database with its own entries, it serves as a Denial Of Service
   attack, because no mail from unknown destinations will be accepted anymore.

   Setting the limit somewhat high (the defautl is 10000 entries in greylist
   database) mitigiates this issue to a certain extent. It is planned, however,
   to implement more sophisticated rules, for example installing limits based on
   IP ranges or client_name:s in general.
3. There is a ``stats.py`` which extracts some statistics from the
   database. This can be useful to detect spam waves or just for graph
   awesomeness.

Dependencies
------------

* SQLite-enabled Python (≥ 3.1)

Usage
-----

It is a drop-in replacement for ``greylist.pl``. Refer to the Postfix manual on
[how to install ``greylist.pl``][0].


   [0]: http://www.postfix.org/SMTPD_POLICY_README.html#greylist
