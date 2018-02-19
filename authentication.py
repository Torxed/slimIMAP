from pam import pam as pamd
try:
	from helpers import dCheck
except:
	import imp, importlib.machinery
	from os.path import basename
	def custom_load(path, namespace=None):
		if not namespace: namespace = basename(path).replace('.py', '').replace('.', '_')

		loader = importlib.machinery.SourceFileLoader(namespace, path)
		handle = loader.load_module(namespace)
		return handle
		
	handle = custom_load('/usr/lib/slimIMAP/helpers.py')
	dCheck = handle.dCheck

#from configuration import config

LOGIN_ATTEMPTS = {}

class internal():
	def __init__(self):
		pass

	def authenticate(self, username, password):
		if type(username) == bytes: username = username.decode('UTF-8')
		if type(password) == bytes: password = password.decode('UTF-8')

		if dCheck(config, 'users') and dCheck(config['users'], username):
			if dCheck(config['users'][username], 'password') == password:
				log('{} has successfully logged in.'.format(username), product='slimIMAP', handler='auth_internal', level=2)
				if username in LOGIN_ATTEMPTS: del(LOGIN_ATTEMPTS[username])
				return True

		if not username in LOGIN_ATTEMPTS: LOGIN_ATTEMPTS[username] = 0
		LOGIN_ATTEMPTS[username] += 1

		log('{} has {} failed INTERNAL login attempts.'.format(username, LOGIN_ATTEMPTS[username]), product='slimIMAP', handler='auth_internal', level=1)
		return False

class pam():
	def __init__(self):
		self.pam = pamd()

	def authenticate(self, username, password):
		if type(username) == bytes: username = username.decode('UTF-8')
		if type(password) == bytes: password = password.decode('UTF-8')

		if self.pam.authenticate(username, password):
			log('{} has successfully logged in.'.format(username), product='slimIMAP', handler='auth_pam', level=2)
			if username in LOGIN_ATTEMPTS: del(LOGIN_ATTEMPTS[username])
			return True

		if not username in LOGIN_ATTEMPTS: LOGIN_ATTEMPTS[username] = 0
		LOGIN_ATTEMPTS[username] += 1

		log('{} has {} failed PAM based login attempts.'.format(username, LOGIN_ATTEMPTS[username]), product='slimIMAP', handler='auth_pam', level=1)
		return False