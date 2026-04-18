import axios from 'axios';

import type { SignupBody } from '@openapi';

import { getBaseApiUrl } from './adapter';

const signupAxios = axios.create({ baseURL: getBaseApiUrl() });

export async function getSignupInfo(signup_token: string) {
  return signupAxios.get(`/signup/${signup_token}`);
}

export async function submitSignup(signup_token: string, body: SignupBody) {
  return signupAxios.post(`/signup/${signup_token}`, body);
}
