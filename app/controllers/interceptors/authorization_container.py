import logging
from functools import wraps
from casbin import Enforcer


class AuthorizationContainer:
    '''A singleton instance for casbin enforcer'''

    _instance = None

    @classmethod
    def instance(cls, app=None, enforcer=None, adapter=None):
        if cls._instance is None:
            cls._instance = cls(app, enforcer, adapter)
        return cls._instance

    def __init__(self, app=None, enforcer=None, adapter=None):
        """
        Args:
            app (object): Flask App object to get Casbin Model
            enforcer (object): Casbin Enforcer
            adapter (object): Casbin Adapter
        """
        self.app = app
        self.adapter = adapter
        self.enforcer = enforcer
        self._owner_loader = None
        self.user_name_headers = None
    
    def getEnforcer(self) -> Enforcer:
        return self.enforcer
