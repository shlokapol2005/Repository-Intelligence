export const PI = 3.14;
export let counter = 0;

export function add(a, b) {
  return a + b;
}

export class Calculator {
  compute() {
    return 1;
  }
}

const helperA = 1;
const helperB = 2;
export { helperA, helperB };

const x = 1, y = 2;
module.exports = { x, y };
