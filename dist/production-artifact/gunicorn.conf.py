import collections
import collections.abc

# Python 3.10+ compatibility patch for gevent-websocket and legacy libraries
for name in dir(collections.abc):
    if not name.startswith('_'):
        setattr(collections, name, getattr(collections.abc, name))
