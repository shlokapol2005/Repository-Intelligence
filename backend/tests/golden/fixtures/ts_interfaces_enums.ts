export interface Point {
  x: number;
  y: number;
}

export enum Role {
  Admin,
  User,
}

@Injectable()
export class UserService {
  async getUser(id: string): Promise<Point | null> {
    return null;
  }
}
