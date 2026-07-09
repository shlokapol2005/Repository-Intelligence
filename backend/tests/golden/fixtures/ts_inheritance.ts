export class Animal {
  move(): void {}
}

export class Dog extends Animal {
  bark(): void {}
}

export class Cat extends Animal implements Pet, Comparable {
  meow(): void {}
}

export class Box<T> extends Container<T> {}
