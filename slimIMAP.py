import shlex
import imp, importlib.machinery, signal, re
from ssl import wrap_socket, CERT_NONE, SSLError
from socket import *
from select import epoll, EPOLLIN, EPOLLOUT, EPOLLHUP
from base64 import b64encode, b64decode
from time import sleep, strftime, localtime, time
from os import remove, getpid, kill, chown
from os.path import basename
from json import loads, dumps

def custom_load(path, namespace=None):
	if not namespace: namespace = basename(path).replace('.py', '').replace('.', '_')

	loader = importlib.machinery.SourceFileLoader(namespace, path)
	handle = loader.load_module(namespace)
	return handle

## Custom library imports.
## Upon cloning or running locally, they usually reside in the same folder.
## But upon "installation" they might be moved to /usr/lib to not clutter down /usr/bin.
## - Also the config is assumed to live under /etc/slimIMAP if not locally
try:
	from configuration import config as local_conf
except:
	handle = custom_load('/etc/slimIMAP/configuration.py')
	local_conf = handle.config

try:
	from authentication import internal, pam
except:
	handle = custom_load('/usr/lib/slimIMAP/authentication.py')
	internal = handle.internal
	pam = handle.pam

try:
	from helpers import generate_UID, dCheck, log as logger, safeDict, signal_handler#, postgres
except:
	handle = custom_load('/usr/lib/slimIMAP/helpers.py')
	#postgres = handle.postgres
	generate_UID = handle.generate_UID
	dCheck = handle.dCheck
	logger = handle.log
	safeDict = handle.safeDict
	signal_handler = handle.signal_handler

__builtins__.__dict__['log'] = logger
__builtins__.__dict__['config'] = local_conf

__date__ = '2018-02-19 21:54 CET'
__version__ = '0.0.1'
__author__ = 'Anton Hvornum'

runtimemap = {'_poller' : epoll(),
			  '_sockets' : {},
			  '_supports' : ['SIZE 10240000', 'STARTTLS', 'AUTH PLAIN LOGIN', 'ENHANCEDSTATUSCODES', '8BITMIME', 'DSN'],
			  '_login_methods' : {'_pam' : pam(), 'postgresql' : None, 'internal' : internal()},
			  '_clients' : {}
		   }

__builtins__.__dict__['runtime'] = runtimemap

def drop_privileges():
	return True

class client():
	def __init__(self, socket, addr, buffert=8192, data_pos=0, data=b'', username=None):
		self.socket = socket
		self.addr = addr
		self.buffer = buffert
		self.data = data
		self.data_pos = data_pos

		self.sslified = False
		self.username = username

	def send(self, bdata, lending=b'\r\n'):
		if not type(bdata) == bytes:
			bdata = bytes(bdata, 'UTF-8')

		try:
			self.socket.send(bdata+lending)
		except BrokenPipeError:
			return terminate_socket(self.socket)

	def non_ssl_command(self, command):
		if command.lower() in ['ehlo', 'starttls']:
			return True
		return False

	def recv(self, buffert=None):
		if not buffert: buffert=self.buffer
		if self.sslified:
			try:
				data = self.socket.read(buffert)
			except SSLError:
				log('Unknown CA or broken pipe.')

		else:
			data = self.socket.recv(buffert)

		if len(data) <= 0:
			return terminate_socket(self.socket)
		self.data += data

		return True

	def parse(self):
		pass

def terminate_socket(socket):
	runtime['_poller'].unregister(socket.fileno())
	del(runtime['_clients'][socket.fileno()])
	socket.close()
	return False

class mail_delivery(client):
	def __init__(self, socket, addr, mail_id, mail_len, mailbox='draft', *args, **kwargs):
		client.__init__(self, socket, addr, *args, **kwargs)
		self.mailbox = mailbox
		self.len = int(mail_len)
		self._id = mail_id
		self.data_recieved = 0
		self.message = b''

	def parse(self):
		if len(self.data):
			if not b'\r\n' in self.data[self.data_pos:]:
				return False

			next_pos = self.data_pos
			for line in self.data[self.data_pos:].split(b'\r\n'):
				if len(line) <= 0:
					next_pos += 2
					continue

				self.message += line + b'\r\n'
				self.data_recieved += len(line+b'\r\n')
				if self.data_recieved >= self.len:
					log('Store complete of mail {} in {}'.format(self._id, self.mailbox), host=self.addr, product='slimIMAP', handler='mail_delivery', level=1)
					self.send(self._id + b' OK APPEND completed')
					runtime['_clients'][self.socket.fileno()] = authenticated(self.socket, self.addr, username=self.username, data=self.data, data_pos=self.data_pos+next_pos+len(line+b'\r\n'))

				next_pos += len(line)
			self.data_pos = next_pos

class authenticated(client):
	def __init__(self, socket, addr, *args, **kwargs):
		client.__init__(self, socket, addr, *args, **kwargs)

	def parse(self):
		if len(self.data):
			if not b'\r\n' in self.data[self.data_pos:]:
				return False

			next_pos = self.data_pos
			for line in self.data[self.data_pos:].split(b'\r\n'):
				if len(line) <= 0:
					next_pos += 2
					continue

				_id, command = line.split(b' ', 1)
				if self.username:
					if b'logout' == command[:len('logout')].lower():
						self.send('* BYE IMAP4rev1 Server logging out')
						self.send(_id + b' OK LOGOUT completed')
						runtime['_clients'][self.socket.fileno()] = pre_auth(self.socket, self.addr, username=None, data=b'', data_pos=0)

					elif b'list' == command[:len('list')].lower():
						command = command.decode('UTF-8')
						list_data = shlex.split(command)
						trash, path, search_arguments = list_data
						log('User is listing mailbox {}/{}'.format(path, search_arguments), host=self.addr, product='slimIMAP', handler='authenticated', level=2)
						self.send('* LIST (\\HasNoChildren) "{}" "{}"'.format(("/" if not len(path) else path), search_arguments))
						self.send(_id + b' OK LIST Completed')
					elif b'create' == command[:len('create')].lower():
						command = command.decode('UTF-8')
						temp = shlex.split(command)
						log('User is creating mailbox {}'.format(temp[1]), host=self.addr, product='slimIMAP', handler='authenticated', level=5)
						self.send(_id + b' OK CREATE completed.')
					elif b'select' == command[:len('select')].lower():
						trash, box = command.split(b' ', 1)
						log('User selected mailbox {}'.format(box), host=self.addr, product='slimIMAP', handler='authenticated', level=1)
						self.send('* {} EXISTS'.format(0)) # How many mails
						self.send('* {} RECENT'.format(0)) # How many new mails
						self.send('* OK [UNSEEN {}] Message {} is first unseen'.format(0, 0))
						self.send('* OK [UIDVALIDITY {}] UIDs valid'.format(0))
						self.send('* OK [UIDNEXT {}] Predicted next UID'.format(generate_UID()))
						self.send('* FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)')
						self.send('* OK [PERMANENTFLAGS (\\Deleted \\Seen \\*)] Limited')
						self.send(_id + b' OK [READ-WRITE] SELECT completed.')
					elif b'append' == command[:len('append')].lower():
						command = command.decode('UTF-8')
						command_split = shlex.split(command)
						mailbox = command_split[1]
						options = command_split[2].strip('()')
						mail_len = command_split[3].strip('{}')
						self.send('+ Ready for literal data')
						log('User is storing mail {} in {}, with a length of {}'.format(_id, mailbox, mail_len), host=self.addr, product='slimIMAP', handler='authenticated', level=2)
						runtime['_clients'][self.socket.fileno()] = mail_delivery(self.socket, self.addr, mail_id=_id, mailbox=mailbox, mail_len=mail_len, username=self.username, data=self.data, data_pos=self.data_pos+len(line+b'\r\n'))
					elif b'subscribe' == command[:len('subscribe')].lower():
						tmp = command.decode('UTF-8')
						tmp = shlex.split(tmp)
						mailbox = tmp[1]
						log('User is subscribing to mailbox {}'.format(mailbox), host=self.addr, product='slimIMAP', handler='authenticated', level=2)
						self.send(_id + b' OK SUBSCRIBE completed')
					elif b'lsub' == command[:len('lsub')].lower():
						# {"host": ["127.0.0.1", 43744], "handler": "authenticated", "message": "command \"b'lsub \"\" \"test/*\"'\" is not implemented.", "product": "slimIMAP", "level": 2}
						tmp = command.decode('UTF-8')
						tmp = shlex.split(tmp)
						trash, path, search_criteria = tmp
						self.send('* LSUB () "{}" {}'.format(("/" if not len(path) else path), search_criteria))
						self.send(_id + b' OK LSUB completed')
					elif b'unsubscribe' == command[:len('unsubscribe')].lower():
						tmp = command.decode('UTF-8')
						tmp = shlex.split(tmp)
						#trash, path, search_criteria = tmp
						trash, path = tmp[:2]
						if len(tmp) >= 3:
							search_criteria = tmp[3]
						else:
							search_criteria = None
						self.send(_id + b' OK UNSUBSCRIBE completed')
					# {"host": ["127.0.0.1", 43776], "handler": "authenticated", "message": "command \"b'STATUS \"INBOX\" (UIDNEXT MESSAGES UNSEEN RECENT)'\" is not implemented.", "product": "slimIMAP", "level": 2}
						self.send(_id + b' OK NOOP completed')
					else:
						log('command "{}" is not implemented.'.format(command), host=self.addr, product='slimIMAP', handler='authenticated', level=2)
						self.send(_id + b' BAD Command not implemented.')
				else:
					log('Client has accessed authenticated commands without authenticating!', host=self.addr, product='slimIMAP', handler='authenticated', level=100)
					terminate_socket(self.socket)

				next_pos += len(line)
			self.data_pos = next_pos

class auth_plain(client):
	def __init__(self, socket, addr, *args, **kwargs):
		client.__init__(self, socket, addr, *args, **kwargs)

	def parse(self):
		if len(self.data):
			if not b'\r\n' in self.data[self.data_pos:]:
				return False

			next_pos = self.data_pos
			for line in self.data[self.data_pos:].split(b'\r\n'):
				if len(line) <= 0:
					next_pos += 2
					continue

				_id, command = line.split(b' ', 1)
				if b'authenticate' == command[:len('authenticate')]:
					pass
				elif b'login' == command[:len('login')]:
					tmp = command.decode('UTF-8')
					trash, username, password = shlex.split(tmp)
					#log(authenticating with...)

					for method in runtime['_login_methods']:
						if not runtime['_login_methods'][method]: continue # Disabled method

						if runtime['_login_methods'][method].authenticate(username, password):
							self.send(_id + b' OK LOGIN completed.')
							runtime['_clients'][self.socket.fileno()] = authenticated(self.socket, self.addr, username=username, data=self.data, data_pos=next_pos+len(line+b'\r\n'))
							return True

					log('{} has failed to login!'.format(username), product='slimIMAP', handler='auth_plain', level=10)
					self.send(_id + b' NO login failed, invalid credentials.')
					return terminate_socket(self.socket)
				else:
					log('command "{}" is not implemented.'.format(command), host=self.addr, product='slimIMAP', handler='auth_plain', level=2)

				next_pos += len(line)
			self.data_pos = next_pos

runtime['_auth_methods'] = {b'plain' : auth_plain}

class pre_auth(client):
	def __init__(self, socket, addr, *args, **kwargs):
		client.__init__(self, socket, addr, *args, **kwargs)

	def parse(self):
		if len(self.data):
			if not b'\r\n' in self.data[self.data_pos:]:
				return False

			# 530 5.7.0 Must issue a STARTTLS command first

			next_pos = self.data_pos
			for line in self.data[self.data_pos:].split(b'\r\n'):
				if len(line) <= 0:
					next_pos += 2
					continue

				_id, command = line.split(b' ', 1)
				if b'capability' == command[:len('capability')]:
					self.send(b'* CAPABILITY IMAP4rev1 STARTTLS AUTH=PLAIN')
					self.send(b'LOGINDISABLED')
					self.send(_id + b' OK CAPABILITY completed')
				elif b'starttls' == command[:len('starttls')].lower():
					log('Converted communication with {} to SSL.'.format(self.addr), host=self.addr, product='slimIMAP', handler='pre_auth', level=1)
					self.send(_id + b' OK STARTTLS completed')
					self.socket = wrap_socket(self.socket, keyfile=config['ssl']['key'], certfile=config['ssl']['cert'], server_side=True, do_handshake_on_connect=True, suppress_ragged_eofs=False, cert_reqs=CERT_NONE, ca_certs=None, ssl_version=config['ssl']['VERSION'])
					self.sslified = True
				elif b'authenticate' == command[:len('authenticate')]:
					#TODO: Enforce SSL (or warn about it)!
					# self.send(_id + b' NO authenticate failure, invalid credentials.)
					trash, method = command.split(b' ', 1)
					log('{} wants to authenticate with {}.'.format(self.addr, method), host=self.addr, product='slimIMAP', handler='pre_auth', level=1)
					if method.lower() in runtime['_auth_methods']:
						runtime['_clients'][self.socket.fileno()] = runtime['_auth_methods'][method.lower()](self.socket, self.addr, data=self.data, data_pos=self.data_pos)
						break
					else:
						self.send(_id + b' BAD command unknown or arguments invalid.')
						#self.send(_id + b' NO authenticate failure, invalid credentials.')
						return terminate_socket(self.socket)
				else:
					log('command "{}" is not implemented.'.format(command), host=self.addr, product='slimIMAP', handler='pre_auth', level=2)

				next_pos += len(line)
			self.data_pos = next_pos

runtime['_sockets']['port_143'] = socket()
runtime['_sockets']['port_143'].setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
runtime['_sockets']['port_143'].bind(('', 1339)) # TODO: 25
runtime['_sockets']['port_143'].listen(4)
runtime['_sockets']['port_993'] = socket()
runtime['_sockets']['port_993'].setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
runtime['_sockets']['port_993'].bind(('', 1340))
runtime['_sockets']['port_993'].listen(4)
runtime['_sockets']['port_993'] = wrap_socket(runtime['_sockets']['port_993'], keyfile=config['ssl']['key'], certfile=config['ssl']['cert'], server_side=True, do_handshake_on_connect=True, suppress_ragged_eofs=False, cert_reqs=CERT_NONE, ca_certs=None, ssl_version=config['ssl']['VERSION'])

runtime['_poller'].register(runtime['_sockets']['port_143'].fileno(), EPOLLIN)
runtime['_poller'].register(runtime['_sockets']['port_993'].fileno(), EPOLLIN)

while drop_privileges() is None:
	log('Waiting for privileges to drop.', product='slimIMAP', handler='smtp_main', once=True, level=5)

while 1:
	for fileno, eventid in runtime['_poller'].poll(config['poll_timeout']):
		if fileno == runtime['_sockets']['port_143'].fileno():
			ns, na = runtime['_sockets']['port_143'].accept()
			runtime['_poller'].register(ns.fileno(), EPOLLIN)
			
			log('Welcoming client {}'.format(na), host=na, product='slimIMAP', handler='main_loop', level=2)
			runtime['_clients'][ns.fileno()] = pre_auth(ns, na)
			runtime['_clients'][ns.fileno()].send(b'220 multi-domain.gw ESMTP slimIMAP')
			
		if fileno == runtime['_sockets']['port_993'].fileno():
			ns, na = runtime['_sockets']['port_993'].accept()
			runtime['_poller'].register(ns.fileno(), EPOLLIN)

			log('Welcoming SSL client {}'.format(na), host=na, product='slimIMAP', handler='main_loop', level=2)
			runtime['_clients'][ns.fileno()] = pre_auth(ns, na)
			runtime['_clients'][ns.fileno()].send(b'220 multi-domain.gw ESMTP slimIMAP')

		elif fileno in runtime['_clients']:
			if not runtime['_clients'][fileno].recv():
				try:
					runtime['_poller'].unregister(fileno)
					del(runtime['_clients'][fileno])
				except KeyError:
					pass

	#try:
	for fileno in list(runtime['_clients'].keys()):
		if fileno in runtime['_clients']:
			runtime['_clients'][fileno].parse()
	#except RuntimeError:
	#	Dictionary changed size during iteration

runtime['_sockets']['port_993'].close()
runtime['_sockets']['port_143'].close()