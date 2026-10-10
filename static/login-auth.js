import { supabase } from "./supabase-config.js";

function getNextRedirectUrl() {
    try {
        const nextParam = new URLSearchParams(window.location.search).get('next');
        if (nextParam && nextParam.startsWith('/') && !nextParam.startsWith('//') && !nextParam.startsWith('/\\') && !nextParam.includes('\\')) {
            return nextParam;
        }
    } catch (e) {}
    return '/app-shell';
}

/* === Handle OAuth Callback === */
// This handles the redirect from Google/OAuth providers
async function handleOAuthCallback() {
    const hash = window.location.hash ? window.location.hash.substring(1) : '';
    const hashParams = new URLSearchParams(hash);
    const searchParams = new URLSearchParams(window.location.search);

    const errorParam = hashParams.get('error') || searchParams.get('error');
    const errorDesc = hashParams.get('error_description') || searchParams.get('error_description') || hashParams.get('error_message');
    const type = hashParams.get('type') || searchParams.get('type');
    const accessToken = hashParams.get('access_token');

    // Handle OAuth/Email callback errors (e.g., expired token, user cancel)
    if (errorParam) {
        console.warn('Auth callback error:', errorParam, errorDesc);
        let msg = errorDesc ? decodeURIComponent(errorDesc).replace(/\+/g, ' ') : 'Authentication failed';
        if (msg.toLowerCase().includes('expired') || errorParam.includes('otp_expired')) {
            msg = 'This confirmation link has expired or has already been used. Please try again.';
        } else if (msg.toLowerCase().includes('access_denied')) {
            msg = 'Sign-in request was cancelled or access denied.';
        }
        if (errorMsgGoogleSignIn) errorMsgGoogleSignIn.textContent = msg;
        else if (errorMsgEmail) errorMsgEmail.textContent = msg;
        window.location.hash = '';
        return;
    }

    if (accessToken) {
        // If recovery token and not already on reset confirmation page, forward there
        if (type === 'recovery' && !window.location.pathname.includes('reset-password-confirm')) {
            window.location.href = '/reset-password-confirm' + window.location.hash;
            return;
        }

        console.log('Auth callback detected, token found:', accessToken.substring(0, 20) + '...');
        try {
            const response = await fetch('/auth', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                credentials: 'same-origin'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                console.log('Login successful, redirecting');
                if (window.AbhiHubAnalytics) {
                    window.AbhiHubAnalytics.track('login', { method: type === 'signup' ? 'email_verification' : 'google_oauth' });
                } else if (window.AbhiHubTracking) {
                    window.AbhiHubTracking.trackLogin(type === 'signup' ? 'email_verification' : 'google_oauth');
                }
                window.location.hash = '';
                window.location.href = getNextRedirectUrl();
            } else {
                console.error('Backend login failed:', data.message);
                const failMsg = data.message || 'Authentication session could not be established.';
                if (errorMsgGoogleSignIn) errorMsgGoogleSignIn.textContent = failMsg;
                else if (errorMsgEmail) errorMsgEmail.textContent = failMsg;
                window.location.hash = '';
            }
        } catch (error) {
            console.error('Error during OAuth callback:', error);
            const errText = 'Network error during sign-in. Please try again.';
            if (errorMsgGoogleSignIn) errorMsgGoogleSignIn.textContent = errText;
            else if (errorMsgEmail) errorMsgEmail.textContent = errText;
            window.location.hash = '';
        }
    }
}

// Run on page load
if (window.location.hash || window.location.search.includes('error=')) {
    console.log('Auth params detected on page load');
    handleOAuthCallback();
}

/* == UI - Elements == */
const signInWithGoogleButtonEl = document.getElementById("sign-in-with-google-btn")
const signUpWithGoogleButtonEl = document.getElementById("sign-up-with-google-btn")
const emailInputEl = document.getElementById("email-input")
const passwordInputEl = document.getElementById("password-input")
const signInButtonEl = document.getElementById("sign-in-btn")
const createAccountButtonEl = document.getElementById("create-account-btn")
const emailForgotPasswordEl = document.getElementById("email-forgot-password")
const forgotPasswordButtonEl = document.getElementById("forgot-password-btn")

const errorMsgEmail = document.getElementById("email-error-message")
const errorMsgPassword = document.getElementById("password-error-message")
const errorMsgGoogleSignIn = document.getElementById("google-signin-error-message")



/* == UI - Event Listeners == */
if (signInWithGoogleButtonEl && signInButtonEl) {
    signInWithGoogleButtonEl.addEventListener("click", authSignInWithGoogle)
    signInButtonEl.addEventListener("click", authSignInWithEmail)
}

if (createAccountButtonEl) {
    createAccountButtonEl.addEventListener("click", authCreateAccountWithEmail)
}

if (signUpWithGoogleButtonEl) {
    signUpWithGoogleButtonEl.addEventListener("click", authSignUpWithGoogle)
}

if (forgotPasswordButtonEl) {
    forgotPasswordButtonEl.addEventListener("click", resetPassword)
}




/* === Main Code === */

/* = Functions - Supabase Authentication = */

// Error handling function
function handleLogging(error, context) {
    console.error(`${context}:`, error);
    if (errorMsgGoogleSignIn) {
        errorMsgGoogleSignIn.textContent = error.message || 'An error occurred during authentication';
    }
}

// Function to sign in with Google authentication
async function authSignInWithGoogle() {
    try {
        console.log('Starting Google authentication');

        // Clear previous errors
        errorMsgGoogleSignIn.textContent = '';

        // Attempt to sign in with Google via Supabase
        const { data, error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: window.location.origin // Redirect back to root, callback handler will catch it
            }
        });

        if (error) {
            console.error('Google OAuth error:', error);
            throw new Error('Authentication failed: ' + error.message);
        }

        console.log('Google OAuth redirect initiated');

    } catch (error) {
        console.error('Error during sign-in with Google:', error);
        if (errorMsgGoogleSignIn) {
            errorMsgGoogleSignIn.textContent = error.message || 'Google sign-in failed. Please try again.';
        }
    }
}



// Function to create new account with Google auth - will also sign in existing users
async function authSignUpWithGoogle() {
    try {
        console.log('Starting Google signup/authentication');

        // Clear previous errors
        errorMsgGoogleSignIn.textContent = '';

        const { data, error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: window.location.origin // Redirect back to root
            }
        });

        if (error) {
            console.error('Google OAuth error:', error);
            throw new Error('Authentication failed: ' + error.message);
        }

        console.log('Google OAuth redirect initiated');

    } catch (error) {
        console.error("Error during Google signup: ", error.message);
        if (errorMsgGoogleSignIn) {
            errorMsgGoogleSignIn.textContent = error.message || 'Google authentication failed. Please try again.';
        }
    }
}




function authSignInWithEmail() {
    const email = emailInputEl?.value?.trim();
    const password = passwordInputEl?.value;

    // Clear previous errors
    if (errorMsgEmail) errorMsgEmail.textContent = '';
    if (errorMsgPassword) errorMsgPassword.textContent = '';
    if (errorMsgGoogleSignIn) errorMsgGoogleSignIn.textContent = '';

    // Validate inputs
    if (!email) {
        if (errorMsgEmail) errorMsgEmail.textContent = 'Email is required';
        return;
    }
    if (!password) {
        if (errorMsgPassword) errorMsgPassword.textContent = 'Password is required';
        return;
    }

    if (signInButtonEl) {
        signInButtonEl.disabled = true;
        signInButtonEl.dataset.originalText = signInButtonEl.textContent;
        signInButtonEl.textContent = 'Signing in...';
    }

    console.log('Attempting email login for:', email);

    supabase.auth.signInWithPassword({
        email: email,
        password: password
    })
        .then(({ data, error }) => {
            if (error) {
                console.error('Sign in error:', error);
                throw error;
            }

            if (!data || !data.user || !data.session) {
                throw new Error('Invalid response from authentication service');
            }

            console.log('Login successful for:', data.user.email);
            loginUser(data.user, data.session.access_token);
        })
        .catch((error) => {
            if (signInButtonEl) {
                signInButtonEl.disabled = false;
                signInButtonEl.textContent = signInButtonEl.dataset.originalText || 'Sign In';
            }
            console.error('Login error:', error.message);
            const errStr = (error.message || '').toLowerCase();

            if (errStr.includes('invalid login credentials') || errStr.includes('invalid credentials')) {
                if (errorMsgPassword) errorMsgPassword.textContent = 'Invalid email or password';
            } else if (errStr.includes('invalid email')) {
                if (errorMsgEmail) errorMsgEmail.textContent = 'Invalid email format';
            } else if (errStr.includes('user not confirmed') || errStr.includes('email not confirmed')) {
                if (errorMsgEmail) {
                    errorMsgEmail.innerHTML = 'Email not confirmed yet. <a href="#" id="resend-login-confirm" style="color:#4285f4;text-decoration:underline;">Resend link</a>';
                    document.getElementById('resend-login-confirm')?.addEventListener('click', async (e) => {
                        e.preventDefault();
                        try {
                            await supabase.auth.resend({ type: 'signup', email: email });
                            errorMsgEmail.textContent = 'Confirmation link resent! Please check your inbox (and spam).';
                        } catch (resendErr) {
                            errorMsgEmail.textContent = resendErr.message || 'Could not resend email right now. Try again later.';
                        }
                    });
                }
            } else if (errStr.includes('rate limit')) {
                if (errorMsgPassword) errorMsgPassword.textContent = 'Too many failed login attempts. Please wait a few minutes.';
            } else {
                if (errorMsgPassword) errorMsgPassword.textContent = error.message || 'Login failed. Please try again.';
            }
        });
}



function authCreateAccountWithEmail() {
    const email = emailInputEl?.value?.trim();
    const password = passwordInputEl?.value;

    // Clear previous errors
    if (errorMsgEmail) errorMsgEmail.textContent = '';
    if (errorMsgPassword) errorMsgPassword.textContent = '';
    if (errorMsgGoogleSignIn) errorMsgGoogleSignIn.textContent = '';

    // Validate inputs
    if (!email) {
        if (errorMsgEmail) errorMsgEmail.textContent = 'Email is required';
        return;
    }
    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        if (errorMsgEmail) errorMsgEmail.textContent = 'Please enter a valid email address';
        return;
    }
    if (!password) {
        if (errorMsgPassword) errorMsgPassword.textContent = 'Password is required';
        return;
    }
    if (password.length < 6) {
        if (errorMsgPassword) errorMsgPassword.textContent = 'Password must be at least 6 characters';
        return;
    }

    if (createAccountButtonEl) {
        createAccountButtonEl.disabled = true;
        createAccountButtonEl.dataset.originalText = createAccountButtonEl.textContent;
        createAccountButtonEl.textContent = 'Creating account...';
    }

    console.log('Attempting signup for:', email);

    supabase.auth.signUp({
        email: email,
        password: password,
        options: {
            data: {
                name: email.split('@')[0] // Default name from email
            }
        }
    })
        .then(async ({ data, error }) => {
            if (error) {
                console.error('Signup error:', error);
                throw error;
            }

            if (!data || !data.user) {
                throw new Error('Failed to create user account');
            }

            const user = data.user;
            console.log('Signup successful for:', user.email);

            // Capture referral code from the signup URL (?ref=ABHI-XXXXXX)
            const _refCode = new URLSearchParams(window.location.search).get('ref');
            if (_refCode) {
                try { sessionStorage.setItem('abhihub_ref_code', _refCode); } catch (e) {}
            }

            // Try to create user profile
            try {
                await supabase
                    .from('profiles')
                    .insert([{
                        id: user.id,
                        email: user.email,
                        name: user.user_metadata?.name || email.split('@')[0]
                    }])
                    .select();

                console.log('User profile created');
            } catch (profileError) {
                console.warn('Could not create profile:', profileError);
            }

            // If email confirmation is disabled, session will be returned
            if (data.session) {
                console.log('Auto-login after signup');
                if (window.AbhiHubAnalytics) {
                    window.AbhiHubAnalytics.track('sign_up', { method: 'email' });
                } else if (window.AbhiHubTracking) {
                    window.AbhiHubTracking.trackSignup('email');
                }
                const idToken = data.session.access_token;
                loginUser(user, idToken);
            } else {
                if (createAccountButtonEl) {
                    createAccountButtonEl.disabled = false;
                    createAccountButtonEl.textContent = createAccountButtonEl.dataset.originalText || 'Create Account';
                }
                // Email confirmation is required
                if (errorMsgEmail) {
                    errorMsgEmail.style.color = '#188038';
                    errorMsgEmail.innerHTML = '✅ Account created! We sent a confirmation link to <b>' + user.email +
                        '</b>. Click it to verify your account. ' +
                        '<a href="#" id="resend-confirm-link" style="color:#4285f4;text-decoration:underline;">Resend email</a>';

                    const resendLink = document.getElementById('resend-confirm-link');
                    if (resendLink) {
                        resendLink.addEventListener('click', async (ev) => {
                            ev.preventDefault();
                            try {
                                await supabase.auth.resend({ type: 'signup', email: user.email });
                                errorMsgEmail.innerHTML = '📨 Confirmation email resent. Check your inbox (and spam).';
                            } catch (e) {
                                errorMsgEmail.textContent = 'Could not resend email. Try again later.';
                            }
                        });
                    }
                }
                clearAuthFields();
            }
        })
        .catch((error) => {
            if (createAccountButtonEl) {
                createAccountButtonEl.disabled = false;
                createAccountButtonEl.textContent = createAccountButtonEl.dataset.originalText || 'Create Account';
            }
            console.error('Signup error:', error.message);
            const errStr = (error.message || '').toLowerCase();

            if (errStr.includes('already registered')) {
                if (errorMsgEmail) {
                    errorMsgEmail.innerHTML = 'This email is already registered. <a href="/login" style="color:#4285f4;text-decoration:underline;">Log in instead</a>';
                }
            } else if (errStr.includes('invalid email')) {
                if (errorMsgEmail) errorMsgEmail.textContent = 'Invalid email format';
            } else if (errStr.includes('password')) {
                if (errorMsgPassword) errorMsgPassword.textContent = 'Password must be at least 6 characters';
            } else if (errStr.includes('rate limit')) {
                if (errorMsgEmail) errorMsgEmail.textContent = 'Too many signup attempts. Please try again later.';
            } else {
                if (errorMsgEmail) errorMsgEmail.textContent = error.message || 'Signup failed. Please try again.';
            }
        });
}



function resetPassword() {
    const emailToReset = emailForgotPasswordEl?.value?.trim();
    const errorEl = document.getElementById("email-error-message") || errorMsgEmail;
    const loadingEl = document.getElementById("loading");

    if (errorEl) errorEl.textContent = '';

    if (!emailToReset) {
        if (errorEl) errorEl.textContent = 'Please enter your email address';
        return;
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(emailToReset)) {
        if (errorEl) errorEl.textContent = 'Please enter a valid email address';
        return;
    }

    if (forgotPasswordButtonEl) {
        forgotPasswordButtonEl.disabled = true;
    }
    if (loadingEl) {
        loadingEl.classList.add('show');
    }

    console.log('Requesting password reset for:', emailToReset);

    supabase.auth.resetPasswordForEmail(emailToReset, {
        redirectTo: window.location.origin + '/reset-password-confirm'
    })
        .then(({ data, error }) => {
            if (loadingEl) loadingEl.classList.remove('show');
            if (forgotPasswordButtonEl) forgotPasswordButtonEl.disabled = false;

            if (error) {
                console.error('Password reset error:', error);
                throw error;
            }

            console.log('Password reset email sent');
            clearInputField(emailForgotPasswordEl);

            // Show success message
            const resetFormView = document.getElementById("reset-password-view");
            const resetSuccessView = document.getElementById("reset-password-confirmation-page");

            if (resetFormView && resetSuccessView) {
                resetFormView.style.display = "none";
                resetSuccessView.style.display = "block";
            } else if (errorEl) {
                errorEl.style.color = '#188038';
                errorEl.textContent = 'Check your email for a password reset link.';
            }
        })
        .catch((error) => {
            if (loadingEl) loadingEl.classList.remove('show');
            if (forgotPasswordButtonEl) forgotPasswordButtonEl.disabled = false;

            console.error('Password reset error:', error.message);
            const errStr = (error.message || '').toLowerCase();
            let errorMessage = 'Failed to send password reset email. Please try again.';

            if (errStr.includes('rate limit')) {
                errorMessage = 'Too many password reset requests. Please wait a few minutes and try again.';
            } else if (errStr.includes('email_not_confirmed')) {
                errorMessage = 'Please confirm your email address first before resetting password.';
            } else if (errStr.includes('user_not_found')) {
                errorMessage = 'Email address not found. Please verify the email and try again.';
            } else if (error.message) {
                errorMessage = error.message;
            }

            if (errorEl) {
                errorEl.style.color = '#d93025';
                errorEl.textContent = errorMessage;
            } else {
                alert(errorMessage);
            }
        });
}



function loginUser(user, idToken) {
    console.log('Sending auth token to backend');

    fetch('/auth', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        credentials: 'same-origin'
    })
        .then(response => {
            console.log('Auth response status:', response.status);
            return response.json().then(data => ({ response, data }));
        })
        .then(({ response, data }) => {
            if (response.ok && data.success) {
                console.log('Backend authentication successful');
                // Apply any referral code captured at signup (after session exists)
                try {
                    const _rc = sessionStorage.getItem('abhihub_ref_code');
                    if (_rc) {
                        fetch('/api/referral/register', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'same-origin',
                            body: JSON.stringify({ code: _rc })
                        }).then(r => r.json()).then(j => {
                            if (j.success) {
                                console.log('[Referral] credited invitee with', j.credit_invitee);
                                sessionStorage.removeItem('abhihub_ref_code');
                            }
                        }).catch(() => {});
                    }
                } catch (e) {}

                if (window.AbhiHubAnalytics) {
                    window.AbhiHubAnalytics.track('login', { method: 'email' });
                } else if (window.AbhiHubTracking) {
                    window.AbhiHubTracking.trackLogin('email');
                }
                window.location.href = getNextRedirectUrl();
            } else {
                if (signInButtonEl) {
                    signInButtonEl.disabled = false;
                    signInButtonEl.textContent = signInButtonEl.dataset.originalText || 'Sign In';
                }
                console.error('Backend authentication failed:', data.message);
                const failMsg = data.message || 'Unable to establish session. Please try again.';
                if (errorMsgPassword) errorMsgPassword.textContent = failMsg;
                else if (errorMsgEmail) errorMsgEmail.textContent = failMsg;
                else alert('Login failed: ' + failMsg);
            }
        })
        .catch(error => {
            if (signInButtonEl) {
                signInButtonEl.disabled = false;
                signInButtonEl.textContent = signInButtonEl.dataset.originalText || 'Sign In';
            }
            console.error('Error during login:', error);
            const netErr = 'Network error during sign-in. Please check your connection and try again.';
            if (errorMsgPassword) errorMsgPassword.textContent = netErr;
            else if (errorMsgEmail) errorMsgEmail.textContent = netErr;
            else alert('Error: ' + error.message);
        });
}



// /* = Functions - UI = */
function clearInputField(field) {
    if (field) {
        field.value = "";
    }
}

function clearAuthFields() {
    clearInputField(emailInputEl);
    clearInputField(passwordInputEl);
}

function logoutUser() {
    console.log('Logging out user');

    fetch('/logout', {
        method: 'GET',
        credentials: 'same-origin'
    })
        .then(response => {
            console.log('Logout response:', response.status);
            window.location.href = '/login';
        })
        .catch(error => {
            console.error('Logout error:', error);
            // Even if logout fails, clear frontend and redirect
            window.location.href = '/login';
        });
}


