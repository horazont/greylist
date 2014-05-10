#!/usr/bin/python3
from datetime import datetime, timedelta

import greylist

dbconn = greylist.get_db()
cursor = dbconn.cursor()
now = datetime.utcnow()

try:

    active_greylist, = cursor.execute(
        """SELECT COUNT(*) FROM greylist
        WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?""",
        (now, greylist.stats_active_threshold)).fetchone()
    total_greylist, = cursor.execute(
        """SELECT COUNT(*) FROM greylist""").fetchone()
    active_whitelist, = cursor.execute(
        """SELECT COUNT(*) FROM whitelist
        WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?""",
        (now, greylist.stats_active_threshold)).fetchone()
    total_whitelist, = cursor.execute(
        """SELECT COUNT(*) FROM whitelist""").fetchone()
finally:
    cursor.close()
    dbconn.close()

print("active_greylist={}".format(active_greylist))
print("total_greylist={}".format(total_greylist))
print("active_whitelist={}".format(active_whitelist))
print("total_whitelist={}".format(total_whitelist))
