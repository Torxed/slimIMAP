from ssl import PROTOCOL_TLSv1

try:
	from storages import maildir
except:
	import imp, importlib.machinery
	from os.path import basename
	def custom_load(path, namespace=None):
		if not namespace: namespace = basename(path).replace('.py', '').replace('.', '_')

		loader = importlib.machinery.SourceFileLoader(namespace, path)
		handle = loader.load_module(namespace)
		return handle

	handle = custom_load('/usr/lib/slimIMAP/storages.py')
	maildir = handle.maildir

config = {'pidfile' : '/var/run/slimIMAP.pid',
		  
		  'DOMAINS' : {'xn--frvirrad-n4a.se' : {}, 'hvornum.se' : {}},
		  'log_level' : 2,
		  'log' : True,
		  'resolve' : False, # Not currently in use.
		  
		  'ssl' : {'enabled' : True,
		  			'forced' : True,
					 'key' : './privkey.key',
					 'cert' : './cert.crt',
					 'VERSION' : PROTOCOL_TLSv1},

		  'login_methods' : ['pam', 'postgresql', 'internal'], #postgresql is not fully implemented

		  'users' : {'anton' : {'password' : 'test', 'storage' : maildir('/home/anton/Maildir/new', owner='anton')} },
		  'mailboxes' : {'anton@hvornum.se' : 'anton', # key=email, value=user it belongs to
		  				 'anton@xn--frvirrad-n4a.se' : 'anton',
						 '*@hvornum.se' : 'anton'}, # This defaults all unknown @hvornum.se recipiants to 'anton'
		  'filepermissions' : {'owner' : 'root', 'group' : 'root', 'mod' : 0x0777},

		  'postgresql' : {'database' : 'slimIMAP', 'username' : 'slimIMAP', 'password' : 'test'},
		  'poll_timeout' : 0.5
		}
