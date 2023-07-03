from app.models import Users

def test_users_model():
    user = Users(name='john')

    assert user.name == 'john'