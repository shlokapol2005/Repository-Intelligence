class Base:
    pass


class Dog(Animal):
    def bark(self):
        pass


class Cat(Animal, Comparable):
    pass


class UserModel(db.Model):
    pass


class Container(Generic[T]):
    pass
