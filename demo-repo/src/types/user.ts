export type Role = 'admin' | 'member';

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  createdAt: Date;
}

export interface NewUser {
  email: string;
  name: string;
  role?: Role;
}
