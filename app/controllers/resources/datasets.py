class DatasetCreateRequest:
    def __init__(self, data):
        self.__data = data

    @property
    def data(self):
        return self.__data
    
class DatasetUpdateRequest:
    def __init__(self, id, name, data):
        self.__id = id
        self.__name = name
        self.__data = data

    @property
    def id(self):
        return self.__id
    @property
    def name(self):
        return self.__name
    @property
    def data(self):
        return self.__data

class DatasetResponse:
    def __init__(self, id, name, data, is_enabled):
        self.__id = id
        self.__name = name
        self.__data = data
        self.__is_enabled = is_enabled

    @property
    def id(self):
        return self.__id
    @property
    def name(self):
        return self.__name
    @property
    def data(self):
        return self.__data
    @property
    def is_enabled(self):
        return self.__is_enabled
    