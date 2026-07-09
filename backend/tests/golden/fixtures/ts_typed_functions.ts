import type { Request, Response } from 'express';

export const handler = (req: Request, res: Response): void => {
  res.send('ok');
};

export const asyncHandler = async (req: Request): Promise<void> => {
  return;
};

export function add(a: number, b: number): number {
  return a + b;
}

export function identity<T>(x: T): T {
  return x;
}
