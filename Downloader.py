# -*- coding: utf-8 -*-

__author__ = 'Mayank Gupta'
__version__ = '1.1'
__license__ = 'License :: MIT License'

import os, sys, socket, json
import threading, ssl, select
from datetime import datetime
import time, re, tempfile
from urllib.parse import unquote
from itertools import cycle

MAX_SOCKET_CHUNK_SIZE = 16 * 1024
MAX_IO_CHUNK_SIZE = 8 * 1024

MAX_CONNECTION = 16
MANUAL_MAX_CONNECTION = 64
CONNECTION_PER_BYTE = 1024 * 1024 * 5

class Response:
	def __init__(self, raw:bytes):
		header_body = raw.split(b"\r\n\r\n")

		if len(header_body) == 1:
			self.raw_header = header_body[0]
		else:
			self.raw_header, self.body = header_body

		header_split = self.raw_header.split(b"\r\n")
		self.log = header_split[0]


		log_split = self.log.decode().split(" ")
		if len(log_split) == 3:
			self.protocol, self.status, self.status_str = self.log.decode().split(" ")

		if len(log_split) > 3:
			self.protocol, self.status, self.status_str = log_split[0], log_split[1], " ".join(log_split[2:])

		self.headers = self.make_header()

		self.allow_multi_connection = False
		self.filename = None
		self.length = 0

		if l:=self.headers.get("content-length"):
			self.length = int(l)

		if "accept-ranges" in self.headers:
			self.allow_multi_connection = True

		if disposition:=self.headers.get("content-disposition"):
			groups = disposition.split(";")
			for group in map(lambda x: x.strip(), groups):
				sgroup = group.split("=")
				if len(sgroup) == 2:
					key, value = sgroup
					setattr(self, key, value)

	def __repr__(self):
		return f"<{self.__class__.__name__} status={self.status} length={self.length}>"

	def make_header(self):
		raw_split = self.raw_header.split(b"\r\n")[1:]
		_header = dict()
		for line in raw_split:
			if not line:
				continue
			broken_line = line.decode().split(":")
			_header[broken_line[0].lower()] = ":".join(broken_line[1:]).strip()

		return _header

class Url:
	def __init__(self, url:str):
		# url = unquote(url)
		search = re.search(r"(?P<scheme>\w+)://(?P<host>[\w\.-]+)(?P<path>.*)", url)

		assert search, "Invalid url"

		for key, value in search.groupdict().items():
			setattr(self, key, value)

		self.scheme = self.scheme.lower()

		if self.scheme == "http":
			self.port = 80

		if self.scheme == "https":
			self.port = 443


class Worker(threading.Thread):
	def __init__(self, init_data:dict, connection:object):
		super().__init__()
		self.init_data = init_data
		self.connection = connection
		self.file = tempfile.NamedTemporaryFile(delete=False)

	def run(self):
		data = self.connection.recv(MAX_SOCKET_CHUNK_SIZE)
		res = Response(data)

		while True:
			data = self.connection.recv(MAX_SOCKET_CHUNK_SIZE)
			if not data:
				break

			self.init_data["bytes_recv"] += len(data)
			self.file.write(data)

		if hasattr(self.connection, "pending"):
			left_bytes = self.connection.pending()
			data = self.connection.recv(left_bytes)
			self.init_data["bytes_recv"] += left_bytes
			self.file.write(data)

		self.file.seek(0)
		self.connection.close()

	def __del__(self):
		self.file.close()
		os.unlink(self.file.name)

class ProcessBar(threading.Thread):
	def __init__(self, init_data:dict):
		super().__init__()
		self.init_data = init_data
		self.len = 50
		self.prefix, self.block, self.suffix = ("[", "■", "]")
		self.empty_space = " "
		self.loading = cycle("\\/-")

		self.time_interval = 0.10

	def run(self):
		block_len = 0
		last_bytes = 0
		while self.len != block_len:
			print("\r", end="")
			block_len = (self.init_data["bytes_recv"]*self.len)//self.init_data["length"]
			download_bytes_in_second = ((self.init_data["bytes_recv"]-last_bytes) * (1//self.time_interval))
			eta = f"{self.init_data['length']//download_bytes_in_second}s"

			eta_str = f" {next(self.loading)} ETA {eta:<20}"
			download_bytes_in_second_str = f"{download_bytes_in_second}bytes/second"
			percentage = f" {next(self.loading)} [{block_len*(100//self.len)}/100]"

			print("downloading "+self.prefix + self.block * block_len + self.empty_space * (self.len-block_len)  + self.suffix + percentage, end="")

			last_bytes = self.init_data["bytes_recv"]
			time.sleep(self.time_interval)

		print("")

class Download:
	def __init__(self, url:str, connection:int=None, filename:str=None, headers:dict=dict()):
		self.url = url
		self.url_obj = Url(self.url)

		self.filename = filename
		self.connection = connection

		self.data = dict(bytes_recv=0, url=self.url_obj, connection=connection, filename=filename)

		self.master_payload = self.make_payload(headers=headers)

	def make_payload(self, bytes_range:list=None, headers:dict=None):
		headers = headers or {
			"user-agent": "MayankFawkes/Bot"
		}
		headers.update({"connection": "close"})

		payload = f'GET {self.url_obj.path} HTTP/1.1\r\nhost: {self.url_obj.host}\r\n'

		if bytes_range:
			bytes_range = list(map(str, bytes_range))
			payload += f"range: bytes={'-'.join(bytes_range)}\r\n"

		for key, value in headers.items():
			payload += f"{key}: {value}\r\n"

		payload += "\r\n"

		return payload.encode()

	def create_connection(self):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.connect((self.url_obj.host, self.url_obj.port))
		if self.url_obj.scheme == "https":
			ssl_cxt = ssl.create_default_context()
			sock = ssl_cxt.wrap_socket(sock, server_hostname=self.url_obj.host)

		return sock

	def proces(self):
		sock = self.create_connection()
		sock.send(self.master_payload)
		rawres = sock.recv(MAX_SOCKET_CHUNK_SIZE)

		res = Response(rawres)

		self.data["length"] = res.length

		if res.status.startswith("3"):
			down = Download(url=res.headers["location"])
			down.proces()
			return

		connection = self.predict_conn(res)
		bytes_ranges = self.get_range(length=res.length, connection=connection)

		workers = []

		for bytes_range in bytes_ranges:
			payload = self.make_payload(bytes_range=bytes_range)

			worker_sock = self.create_connection()
			worker_sock.send(payload)

			w = Worker(init_data=self.data, connection=worker_sock)
			w.start()

			workers.append(w)

		ProcessBar(init_data=self.data).start()

		[worker.join() for worker in workers]

		filename = self.get_filename(response=res)

		with open(filename, "wb") as fp:
			for worker in workers:
				while True:
					chunk = worker.file.read(MAX_IO_CHUNK_SIZE)
					if not chunk:
						break

					fp.write(chunk)

		# print(self.data["bytes_recv"])

	def get_filename(self, response:object):
		if self.filename:
			return self.filename

		if filename:=response.filename:
			return filename

		return unquote(self.url.split("/")[-1].split("?")[0])


	def get_range(self, length:int, connection:int):
		steps = length//connection
		ranges = []
		for n in range(0, length, steps):
			ranges.append([n, n+steps-1])

		return ranges

	def predict_conn(self, response:object):
		if self.connection:
			if self.connection > MANUAL_MAX_CONNECTION:
				self.connection = MANUAL_MAX_CONNECTION

		if not response.allow_multi_connection:
			return self.connection or 1

		if self.connection:
			return self.connection

		conn = response.length // CONNECTION_PER_BYTE

		if conn > MAX_CONNECTION:
			return MAX_CONNECTION
		
		if not conn:
			return 1

		return conn
		

if __name__ == '__main__':
	link = "https://github.com/docker/compose/releases/download/v2.6.1/docker-compose-linux-x86_64"
	down = Download(url=link)
	down.proces()

