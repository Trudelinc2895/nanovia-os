from api.models.user import User


def test_user_relationships_do_not_eager_load_auth_unrelated_tables():
    assert User.subscriptions.property.lazy == "noload"
    assert User.modules.property.lazy == "noload"
