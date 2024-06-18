class UserModel:
    def __init__(self, email, first_name, last_name, username, password, oura_token=None, oura_refresh=None):
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.password = password
        self.oura_token = oura_token
        self.oura_refresh = oura_refresh

    @staticmethod
    def from_dict(user: dict):
        user = UserModel(email=user.get('email'), 
                         first_name=user.get('firstName'),
                         last_name=user.get('lastName'),
                         username=user.get('username'),
                         password=user.get('password'),
                         oura_token=user.get('ouraToken'),
                         oura_refresh=user.get('ouraRefresh'))
        return user
    
    def to_dict(self):
        return {
            'email': self.email,
            'firstName': self.first_name,
            'lastName': self.last_name,
            'username': self.username,
            'password': self.password,
            'ouraToken': self.oura_token,
            'ouraRefresh': self.oura_refresh,
        }