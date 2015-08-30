# -*- coding: utf-8 -*-

## Tango-RedPitaya -- Tango device server for RedPitaya multi-istrument board
## Solaris <synchrotron.pl>
## Copyright (C) 2015 Grzegorz Kowalski <daneos@daneos.com>
## See LICENSE for legal information


from PyTango import AttrQuality, AttrWriteType, AttrDataFormat, DispLevel, DevState
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command, device_property

from PyRedPitaya.pc import RedPitaya
from rpyc import connect

from urllib2 import urlopen
import json


class RedPitayaBoard(Device):
	""" RedPitaya device server class """
	__metaclass__ = DeviceMeta


	### RPyC connection details -----------------------------------------------

	host = device_property(dtype=str)							# board hostname
	port = device_property(dtype=int, default_value=18861)		# board port
	reconnect = device_property(dtype=int, default_value=10)	# max reconnect attepts


	### Utilities -------------------------------------------------------------

	def connection_error(self, e):
		""" Set status message informing about connection error and appropiate state """
		self._state = DevState.FAULT
		self.status_message = "Could not connect to the board @ %s:%d\nError message: %s\n" % (self.host, self.port, str(e))
		self.status_message += "Reconnect attempt %d / %d\n" % (self.reconnect_tries, self.reconnect)
		if self.reconnect_tries == self.reconnect:
			self.status_message += "Not trying again."

	def app_error(self, e):
		""" Set status message informing about web application error """
		self._state = DevState.STANDBY
		self.status_message = "Could not connect to webapp @ %s. Error message: %s\n" % (self.host, str(e))
		self.status_message += "You need to have scope (Oscilloscope) webapp installed on your device.\n"
		self.status_message += "Only input acquisition is affected, you can use all other functions anyway."

	def set_state_ok(self, state):
		""" Sets state of normal operation and clears status message """
		self._state = state
		self.status_message = ""

	def board_connect(self):
		""" Connect to the board """
		try:
			self.conn = connect(self.host, self.port)
			self.RP = RedPitaya(self.conn)
		except Exception as e:
			self.connection_error(e)
		else:
			self.set_state_ok(DevState.ON)

	def start_scope_app(self):
		""" Start scope app for data acquisition """
		try:
			res = urlopen("http://%s/bazaar?start=scope" % self.host)
			data = json.loads(res.read())
			if data["status"] != "OK":
				self.app_error("Device didn't start the app: %s" % data["reason"])
		except Exception as e:
			self.app_error(e)
		else:
			self.set_state_ok(DevState.RUNNING)

	def stop_scope_app(self):
		""" Stop scope app """
		try:
			res = urlopen("http://%s/bazaar?stop=" % self.host)
			data = json.loads(res.read())
			if data["status"] != "OK":
				self.app_error("Device didn't stop the app: %s" % data["reason"])
				return
		except Exception as e:
			self.app_error(e)
		else:
			self.set_state_ok(DevState.ON)

	def start_generator(self, channel, opts):
		""" Start signal generator decribed by opts on desired output channel.
			Purpose of this function is to minimize argument count (and therefore mistake possibilities)
			to the Tango accessible generator functions """
		# TODO: Some sanity checking on arguments
		command = "/opt/bin/generate %d %s" % (channel, opts)
		self.conn.root.run_command(command)

	def scope_active_func(self):
		""" Get scope status. It's here, because there is no way of reading the attribute inside the server.
			(At least no documented way...) """
		try:
			res = urlopen("http://%s/data" % self.host)
			rstatus = json.loads(res.read())["status"]
		except Exception as e:
			self.app_error(e)
			return False
		else:
			if rstatus == "OK":
				return True
			else:
				return False

	def generator_ch1_active_func(self):
		""" Get generator channel 1 status. The reason of this function existece is the same as scope_active_func """
		return not self.RP.asga.output_zero

	def generator_ch2_active_func(self):
		""" Get generator channel 2 status. The reason of this function existece is the same as scope_active_func """
		return not self.RP.asgb.output_zero


	### Interface methods -----------------------------------------------------

	def init_device(self):
		""" Start device server """
		Device.init_device(self)
		self.reconnect_tries = 0
		self.set_state_ok(DevState.INIT)
		self.board_connect()	# connect to the board

	def dev_status(self):
		""" Display appropiate status message """
		self._status = "Device is in %s state.\n%s" % (self.get_state(), self.status_message)
		self.set_status(self._status)
		return self._status

	def dev_state(self):
		""" Appropiate state handling """
		# if generator or scope is active, state must be RUNNING no matter what
		if self.generator_ch1_active_func() or self.generator_ch2_active_func() or self.scope_active_func():
			self._state = DevState.RUNNING
		self.set_state(self._state)
		return self._state 


	### Attributes ------------------------------------------------------------

	@attribute(label="FPGA Temperature", dtype=float,
			   access=AttrWriteType.READ,
			   unit="*C", format="%4.3f",
			   doc="Temperature of the FPGA chip")
	def temperature(self):
		return self.RP.ams.temp

	@attribute(label="LEDs state", dtype="int",		# plain int type causes errors
			   access=AttrWriteType.READ_WRITE,
			   fset="set_leds",
			   min_value=0, max_value=255,
			   doc="State of the LED indicators")
	def leds(self):
		return self.RP.hk.led
	def set_leds(self, leds):
		self.RP.hk.led = leds

	@attribute(label="Ping check", dtype=str,
			   access=AttrWriteType.READ,
			   doc="Connection ping check")
	def ping(self):
		try:
			self.conn.ping()
		except Exception as e:	# should be PingError, but it's not working
			self.connection_error(e)
			if(self.reconnect_tries < self.reconnect):
				self.reconnect_tries += 1
				self.board_connect()	# try to reconnect if possible
			return "FAILED"
		else:
			self.reconnect_tries = 0	# reset reconnect counter
			return "OK"


	### Oscilloscope attributes -----------------------------------------------

	@attribute(label="Scope active", dtype=bool,
			   access=AttrWriteType.READ_WRITE,
			   fset="set_scope_active",
			   doc="Oscilloscope operation state")
	def scope_active(self):
		return self.scope_active_func()
	def set_scope_active(self, v):
		if v:
			self.start_scope_app()
		else:
			self.stop_scope_app()


	### Generator attributes --------------------------------------------------

	@attribute(label="Generator CH1 active", dtype=bool,
			   access=AttrWriteType.READ,
			   doc="CH1 generator operation state")
	def generator_ch1_active(self):
		return self.generator_ch1_active_func()

	@attribute(label="Generator CH2 active", dtype=bool,
			   access=AttrWriteType.READ,
			   doc="CH2 generator operation state")
	def generator_ch2_active(self):
		return self.generator_ch2_active_func()


	### Voltages --------------------------------------------------------------

	@attribute(label="PINT Voltage", dtype=float,
			   access=AttrWriteType.READ,
			   display_level=DispLevel.EXPERT,
			   unit="V", format="%4.3f",
			   doc="Processing system internal voltage")
	def pint_voltage(self):
		return self.RP.ams.vccpint

	@attribute(label="PAUX Voltage", dtype=float,
			   access=AttrWriteType.READ,
			   display_level=DispLevel.EXPERT,
			   unit="V", format="%4.3f",
			   doc="Processing system auxiliary voltage")
	def paux_voltage(self):
		return self.RP.ams.vccpaux

	@attribute(label="BRAM Voltage", dtype=float,
			   access=AttrWriteType.READ,
			   display_level=DispLevel.EXPERT,
			   unit="V", format="%4.3f",
			   doc="RAM blocks voltage")
	def bram_voltage(self):
		return self.RP.ams.vccbram

	@attribute(label="INT Voltage", dtype=float,
			   access=AttrWriteType.READ,
			   display_level=DispLevel.EXPERT,
			   unit="V", format="%4.3f",
			   doc="Programmable logic internal voltage")
	def int_voltage(self):
		return self.RP.ams.vccint

	@attribute(label="AUX Voltage", dtype=float,
			   access=AttrWriteType.READ,
			   display_level=DispLevel.EXPERT,
			   unit="V", format="%4.3f",
			   doc="Programmable logic internal voltage")
	def aux_voltage(self):
		return self.RP.ams.vccaux

	@attribute(label="DDR Voltage", dtype=float,
			   access=AttrWriteType.READ,
			   display_level=DispLevel.EXPERT,
			   unit="V", format="%4.3f",
			   doc="DDR I/O voltage")
	def ddr_voltage(self):
		return self.RP.ams.vccddr


	### Oscilloscope commands -------------------------------------------------

	# need to be a command, because as attribute it exceeds data size limit
	@command(dtype_in="int", doc_in="Channel number",
			 dtype_out=[float], doc_out="Scope input data")
	def scope_data(self, ch):
		# data sanity check
		if ch < 1 or ch > 2:
			self.status_message = "Error: Scope channel should be 1 or 2"
			return [0]
		else:
			self.status_message = ""

		try:
			res = urlopen("http://%s/data" % self.host)
			data_full = json.loads(res.read())
			if data_full["status"] != "OK":
				if data_full['status'] != "OK":
					self.app_error("Could not fetch data from webapp: %s" % data_full["reason"])
					return [0]
			data = data_full["datasets"]["g1"][ch-1]["data"]
		except Exception as e:
			self.app_error(e)
			return
		return [x[1] for x in data]		# remove timestamp part		


	### Generator commands ----------------------------------------------------

	@command(dtype_in=str,	# it was supposed to be an array of arguments, but since ATKPanel doesn't support that it had to change
			 doc_in="Start signal generator. Arguments: Vpp amplitude, frequency [Hz], type (sine, sqr, tri)")
	def start_generator_ch1(self, argstr):
		self.start_generator(1, argstr)

	@command(dtype_in=str,	# it was supposed to be an array of arguments, but since ATKPanel doesn't support that it had to change
			 doc_in="Start signal generator. Arguments: Vpp amplitude, frequency [Hz], type (sine, sqr, tri)")
	def start_generator_ch2(self, argstr):
		self.start_generator(2, argstr)

	@command
	def stop_generator_ch1(self):
		self.RP.asga.output_zero = True
		self._state = DevState.ON

	@command
	def stop_generator_ch2(self):
		self.RP.asgb.output_zero = True
		self._state = DevState.ON