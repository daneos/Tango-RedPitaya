# This file should go to /usr/lib/python2.7/site-packages/PyRedPitaya/ directory on the device's SD card

import rpyc
import os
from raw_memory import BoardRawMemory


class MyService(rpyc.Service):
	def on_connect(self):
		print "CONNECTION"
		self._mem = BoardRawMemory()
		self._conn._config.update(dict(
			allow_all_attrs = True,
			allow_pickle = False,
			allow_getattr = True,
			allow_setattr = True,
			allow_delattr = True,
			import_custom_exceptions = True,
			instantiate_custom_exceptions = True,
			instantiate_oldstyle_exceptions = True,
		))

	def exposed_mem(self):
		return self._mem
		pass

	# this allows to execute commands on server
	def exposed_run_command(self, cmd):
		return os.popen(cmd).read()


if __name__=="__main__":
	from rpyc.utils.server import ThreadedServer
	print 'START SERVER'
	t = ThreadedServer(MyService, port = 18861)
	t.start()
