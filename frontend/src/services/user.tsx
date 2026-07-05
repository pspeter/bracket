import { UserToRegister, UserToUpdate } from '@openapi';
import { createAxios, handleRequestError, performMutation } from './adapter';

export async function performLogin(username: string, password: string) {
  const bodyFormData = new FormData();
  bodyFormData.append('grant_type', 'password');
  bodyFormData.append('username', username);
  bodyFormData.append('password', password);

  const { data } = await createAxios()
    .post('token', bodyFormData)
    .catch((err_response: any) => {
      handleRequestError(err_response);
      return { data: null };
    });

  if (data == null) {
    return false;
  }

  localStorage.setItem('login', JSON.stringify(data));

  handleRequestError(data);

  // Reload axios object.
  createAxios();
  return true;
}

export async function updateUser(user_id: number, user: UserToUpdate) {
  // Users aren't tournament-scoped, so there's no tournament-issues key to invalidate.
  return performMutation('put', `users/${user_id}`, user, { invalidateIssues: false });
}

export async function updatePassword(user_id: number, password: string) {
  return performMutation(
    'put',
    `users/${user_id}/password`,
    { password },
    {
      invalidateIssues: false,
    }
  );
}

export async function registerUser(user: UserToRegister, captchaToken: string | null) {
  return performMutation(
    'post',
    'users/register',
    {
      email: user.email,
      name: user.name,
      password: user.password,
      captcha_token: captchaToken,
    },
    { invalidateIssues: false }
  );
}

export async function registerDemoUser(captchaToken: string | null) {
  return performMutation(
    'post',
    'users/register_demo',
    { captcha_token: captchaToken },
    { invalidateIssues: false }
  );
}
