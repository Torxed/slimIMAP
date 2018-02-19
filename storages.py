import getpass, pwd, grp
from os import makedirs, chown, walk
from os.path import isfile, isdir, abspath, expanduser, basename

try:
	from helpers import generate_UID
except:
	import imp, importlib.machinery
	from os.path import basename
	def custom_load(path, namespace=None):
		if not namespace: namespace = basename(path).replace('.py', '').replace('.', '_')

		loader = importlib.machinery.SourceFileLoader(namespace, path)
		handle = loader.load_module(namespace)
		return handle
		
	handle = custom_load('/usr/lib/slimIMAP/helpers.py')
	generate_UID = handle.generate_UID


class maildir():
	def __init__(self, path='~/Maildir', owner=None, group=None):
		self.owner = owner
		self.group = group
		self.uid = None
		self.gid = None
		self.path = abspath(expanduser(path))

		if not isdir(self.path):
			makedirs(self.path)

	def store(self, sender, reciever, message):
		if not self.owner:
			if 'filepermissions' in config and 'owner' in config['filepermissions']:
				self.owner = config['filepermissions']['owner']
			else:
				self.owner = getpass.getuser()
		if not self.group:
			if 'filepermissions' in config and 'group' in config['filepermissions']:
				self.group = config['filepermissions']['group']
			else:
				self.group = getpass.getuser()

		print('Mail will be stored as {}.{}'.format(self.owner, self.group))

		if not self.uid:
			self.uid = pwd.getpwnam(self.owner).pw_uid
		if not self.gid:
			self.gid = grp.getgrnam(self.group).gr_gid
		chown(self.path, self.uid, self.gid)

		destination = '{}/{}.mail'.format(self.path, generate_UID())
		log('Stored mail from {} to reciever {} under \'{}\''.format(sender, reciever, destination), product='slimIMAP', handler='storage_maildir', level=3)
		with open(destination, 'wb') as mail:
			mail.write(message)

		chown(destination, self.uid, self.gid)

		return True
