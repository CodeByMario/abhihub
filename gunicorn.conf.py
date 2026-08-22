import collections
import collections.abc

# Python 3.10+ compatibility patch for gevent-websocket
collections.MutableMapping = collections.abc.MutableMapping
collections.Mapping = collections.abc.Mapping
