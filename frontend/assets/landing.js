const formState = { login: document.querySelector('#login-form'), signup: document.querySelector('#signup-form') };

const showStatus = (id, message, error = false) => {
  const element = document.querySelector(`#${id}`);
  element.textContent = message;
  element.className = `form-status${error ? ' error' : ''}`;
};

const request = async (path, options = {}) => {
  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Request failed.');
  return body;
};

const showForm = (name) => {
  formState.login.hidden = name !== 'login';
  formState.signup.hidden = name !== 'signup';
  document.querySelector('#login-tab').classList.toggle('active', name === 'login');
  document.querySelector('#signup-tab').classList.toggle('active', name === 'signup');
  document.querySelector('#login-tab').setAttribute('aria-selected', name === 'login');
  document.querySelector('#signup-tab').setAttribute('aria-selected', name === 'signup');
};

document.querySelector('#login-tab').addEventListener('click', () => showForm('login'));
document.querySelector('#signup-tab').addEventListener('click', () => showForm('signup'));

formState.login.addEventListener('submit', async (event) => {
  event.preventDefault();
  showStatus('login-status', 'Signing in...');
  const form = new FormData(formState.login);
  try {
    await request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: form.get('email'), password: form.get('password') }) });
    window.location.assign('/app');
  } catch (error) {
    showStatus('login-status', error.message, true);
  }
});

formState.signup.addEventListener('submit', async (event) => {
  event.preventDefault();
  showStatus('signup-status', 'Creating your workspace...');
  const form = new FormData(formState.signup);
  try {
    await request('/api/auth/signup', { method: 'POST', body: JSON.stringify({ email: form.get('email'), password: form.get('password'), business_name: form.get('business_name') }) });
    window.location.assign('/app');
  } catch (error) {
    showStatus('signup-status', error.message, true);
  }
});
