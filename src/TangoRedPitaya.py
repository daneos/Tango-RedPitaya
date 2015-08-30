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
from rpyc.core.protocol import PingError	# btw. this doesn't work


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
		self.set_state(DevState.FAULT)
		self.status_message = "Could not connect to the board @ %s:%d\nError message: %s\n" % (self.host, self.port, str(e))
		self.status_message += "Reconnect attempt %d / %d\n" % (self.reconnect_tries, self.reconnect)
		if self.reconnect_tries == self.reconnect:
			self.status_message += "Not trying again."

	def board_connect(self):
		""" Connect to the board """
		try:
			self.conn = connect(self.host, self.port)
			self.RP = RedPitaya(self.conn)
		except Exception as e:
			self.connection_error(e)
		else:
			self.set_state(DevState.ON)
			self.status_message = ""


	### Interface methods -----------------------------------------------------

	def init_device(self):
		""" Start device server """
		Device.init_device(self)

		self.reconnect_tries = 0

		self.set_state(DevState.INIT)
		self.board_connect()	# connect to the board
		

	def dev_status(self):
		""" Display appropiate status message """
		self._status = "Device is in %s state.\n%s" % (self.get_state(), self.status_message)
		self.set_status(self._status)
		return self._status


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

	@attribute(label="Scope frequency", dtype=float,
			   access=AttrWriteType.READ_WRITE,
			   unit="Hz", format="%4.3f",
			   fset="set_scope_freq",
			   doc="Scope sampling frequency (I guess...)")
	def scope_freq(self):
		return self.RP.scope.frequency
	def set_scope_freq(self, freq):
		self.RP.scope.frequency = freq


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

	# These two were implemented as attributes once, but it didn't work
	@command(dtype_out=[float], doc_out="Input channel 1 data")
	def scope_ch1_data(self):
		return self.RP.scope.data_ch1

	@command(dtype_out=[float], doc_out="Input channel 2 data")
	def scope_ch2_data(self):
		return self.RP.scope.data_ch2


	### Generator commands ----------------------------------------------------

	@command
	def generator_ch1_stop(self):
		self.RP.asga.output_zero = True

	@command
	def generator_ch2_stop(self):
		self.RP.asgb.output_zero = True