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

   To mitigiate this attack, ``greylist.py`` also supports soft-limiting for
   each mail source. By setting this soft limit signifincantly lower than the
   overall limit of the database, an attacker from only a single ``client_name``
   cannot fill the whole database, and purging first happens per
   ``client_name``, and only if that is not sufficient, entries from any
   ``client_name`` are removed from the database, in the order they last
   touched.

3. There is a ``stats.py`` which extracts some statistics from the
   database. This can be useful to detect spam waves or just for graph
   awesomeness.

Dependencies
------------

* SQLite-enabled Python (≥ 3.1)

Configuration and implementation
--------------------------------

Greylisting works on triples of (``sender``, ``recipient``, ``client_name``),
called *greylisting key* in the following text, while ``client_name`` is either
the ``client_name`` supplied by Postfix (that is the host name of the client) or
the ``client_address``. Whitelisting works on ``client_name``.

If a client gets whitelisted, any mail from it will be accepted by
``greylist.py``, and it won’t touch or create any greylisting entries during
that process. This implies that greylisting entries for that ``client_name`` may
expire and may be purged from the database, if any such limits are in place.

After each request, ``greylist.py`` performs garbage collection on the database,
if any limits are enabled.

``greylist.py`` supports some configuration options which might be useful. They
are listed here with their corresponding defaults. To override them, you can
either edit the source (not recommended) or create a ``config.ini`` and put the
values in the ``[DEFAULT]`` section.

    db_file = "greylist.db"

Set the path to the greylisting database file. This must be an existing sqlite3
file with the correct schema or a nonexisting file. If the file does not exist
or has an incorrect schema, it will be recreated.

    greylist_timeout = 60

This is the minimum time since the first request (called ``first_seen``) for a
*greylisting key* for mail to be accepted.

    auto_whitelist_threshold = 10

If more than ``auto_whitelist_threshold`` mails have passed the greylisting test
from one ``client_name`` source, it will be added to the whitelist, surpassing
any further greylisting tests.

    move_to_whitelist = True

If this setting is set to True, all existing greylist entries for a
``client_name`` which is getting auto-whitelisted will be deleted from the
greylist. This helps to keep the greylist clean, but is not recommended if
whitelist entries expire (because the reputation from the greylist entries is
lost) and greylist entries do not.

    max_greylist_entries = 100000
    max_whitelist_entries = 1000

If this is not set to None, if the respective list grows beyond that limit, any
excessive entries will be removed from the database during database garbage
collection. When doing this, ``greylist.py`` will start deletion with the least
recently used entry, so that active entries are preserved.

    max_greylist_entries_per_client_name = 1000

If this is not set to None, a separate limit is imposed for each ``client_name``
in the greylist -- this is a first line of defense against the attack mentioned
in the preface. If a ``client_name`` has more than this amount of greylist
entries, purging for only that client name takes place, leaving other entries
intact. This limit is applied before the general limit. If the general limit is
enabled, then this limit will only be applied if the general limit is already
surpassed.

For this limit, deletions are performed in the **reverse** order, that is, newer
entries are deleted before older ones. This prevents that a legitimate bulk mail
transfer gets stuck in a defer loop.

    greylist_expire = None
    whitelist_expire = None

If this is not set to None, any entries which have not been used for the given
amount of seconds will be purged from the database on database garbage
collection. This happens before enforcing the max limit and is independent of
the max limit.

    stats_active_threshold = 3600
    stats_dead_threshold = 86400

This is only relevant for ``stats.py``: This first is the time interval in
seconds during which entries in any list are considered active. Entries which
have not been used for more than that time interval are not considered
active. Entries which are older than the ``stats_dead_threshold`` and have not
been seen since their first occurence are considered dead.

    response_pass = "action=dunno\n"
    response_fail = "action=defer_if_permit You have been greylisted.\n"

These are the responses of ``greylist.py`` for the respective actions. It is
recommended to leave them at these defaults, except for the message after
``defer_if_permit``. Using exactly these actions will make other rules in
Postfix’ configuration take precedence over ``greylist.py`` with respect to
rejecting mails. ``greylist.py`` will still take precedence for deferring mails,
if no other rule rejects them.

Usage
-----

It is a drop-in replacement for ``greylist.pl``. Refer to the Postfix manual on
[how to install ``greylist.pl``][0].

To fetch the statistics, use:

    ./stats.py -c path/to/config/file

If you do not use a config file, you can omit the ``-c`` argument.


   [0]: http://www.postfix.org/SMTPD_POLICY_README.html#greylist
