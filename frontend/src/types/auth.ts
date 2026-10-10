export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name?: string;
  phone?: string;
  role: string;
  normalized_role?: 'AGENCY_ADMIN' | 'PRACTICE_ADMIN' | 'FRONT_DESK';
  is_agency_admin?: boolean;
  is_practice_admin?: boolean;
  practice?: number | string | null;
  practice_name?: string;
  practice_slug?: string;
  created_at: string;
}

export interface AuthTokens {
  access: string
  refresh: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface GoogleOAuthResponse {
  url: string
}

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
