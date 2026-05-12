import { supabase } from "./supabase-config.js";

/* === Handle OAuth Callback === */
// This handles the redirect from Google/OAuth providers
async function handleOAuthCallback() {
    const hash = window.location.hash.substring(1); // Remove '#'
    const params = new URLSearchParams(hash);
    const accessToken = params.get('access_token');

    if (accessToken) {
        console.log('OAuth callback detected, token found:', accessToken.substring(0, 20) + '...');
        try {
            // Send token to backend to create session
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
                console.log('Login successful, redirecting to dashboard');
                // Track login via GA
                if (window.AbhiHubTracking) {
                    window.AbhiHubTracking.trackLogin('google_oauth', '');
                }
                // Clear the hash and redirect
                window.location.hash = '';
                window.location.href = '/dashboard';
            } else {
                console.error('Backend login failed:', data.message);
                alert('Login failed: ' + (data.message || 'Unknown error'));
                // Clear the hash so user can retry
                window.location.hash = '';
            }
        } catch (error) {
            console.error('Error during OAuth callback:', error);
            alert('Error processing login: ' + error.message);
            window.location.hash = '';
        }
    }
}

// Run on page load
if (window.location.hash) {
    console.log('Hash detected on page load:', window.location.hash.substring(0, 50));
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
    const email = emailInputEl.value?.trim();
    const password = passwordInputEl.value;

    // Clear previous errors
    errorMsgEmail.textContent = '';
    errorMsgPassword.textContent = '';

    // Validate inputs
    if (!email) {
        errorMsgEmail.textContent = 'Email is required';
        return;
    }
    if (!password) {
        errorMsgPassword.textContent = 'Password is required';
        return;
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

            const user = data.user;
            const session = data.session;

            console.log('Login successful for:', user.email);

            // Get the access token and send to backend
            const idToken = session.access_token;
            loginUser(user, idToken);
        })
        .catch((error) => {
            console.error('Login error:', error.message);

            if (error.message?.includes('Invalid login credentials')) {
                errorMsgPassword.textContent = 'Invalid email or password';
            } else if (error.message?.includes('invalid email')) {
                errorMsgEmail.textContent = 'Invalid email format';
            } else if (error.message?.includes('User not confirmed')) {
                errorMsgEmail.textContent = 'Please confirm your email before logging in';
            } else if (error.message?.includes('Email not confirmed')) {
                errorMsgEmail.textContent = 'Check your email for a confirmation link';
            } else {
                errorMsgPassword.textContent = error.message || 'Login failed. Please try again.';
            }
        });
}



function authCreateAccountWithEmail() {
    const email = emailInputEl.value?.trim();
    const password = passwordInputEl.value;

    // Clear previous errors
    errorMsgEmail.textContent = '';
    errorMsgPassword.textContent = '';

    // Validate inputs
    if (!email) {
        errorMsgEmail.textContent = 'Email is required';
        return;
    }
    if (!password) {
        errorMsgPassword.textContent = 'Password is required';
        return;
    }
    if (password.length < 6) {
        errorMsgPassword.textContent = 'Password must be at least 6 characters';
        return;
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        errorMsgEmail.textContent = 'Please enter a valid email address';
        return;
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
                // Don't fail signup if profile creation fails
            }

            // If email confirmation is disabled, session will be returned
            if (data.session) {
                console.log('Auto-login after signup');
                // Track signup via GA
                if (window.AbhiHubTracking) {
                    window.AbhiHubTracking.trackSignup('email', user?.email || '');
                }
                const idToken = data.session.access_token;
                loginUser(user, idToken);
            } else {
                // Email confirmation is required
                errorMsgEmail.textContent = 'Account created! Check your email for confirmation link';
                console.log('Email confirmation required for:', user.email);

                // Clear input fields
                clearAuthFields();

                // Show success message for a few seconds
                setTimeout(() => {
                    errorMsgEmail.textContent = '';
                }, 5000);
            }
        })
        .catch((error) => {
            console.error('Signup error:', error.message);

            if (error.message?.includes('already registered')) {
                errorMsgEmail.textContent = 'This email is already registered. Try logging in instead.';
            } else if (error.message?.includes('invalid email')) {
                errorMsgEmail.textContent = 'Invalid email format';
            } else if (error.message?.includes('password')) {
                errorMsgPassword.textContent = 'Password must be at least 6 characters';
            } else if (error.message?.includes('Email rate limit')) {
                errorMsgEmail.textContent = 'Too many signup attempts. Please try again later.';
            } else {
                errorMsgEmail.textContent = error.message || 'Signup failed. Please try again.';
            }
        });
}



function resetPassword() {
    const emailToReset = emailForgotPasswordEl.value?.trim();

    if (!emailToReset) {
        alert('Please enter your email address');
        return;
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(emailToReset)) {
        alert('Please enter a valid email address');
        return;
    }

    console.log('Requesting password reset for:', emailToReset);

    supabase.auth.resetPasswordForEmail(emailToReset, {
        redirectTo: window.location.origin + '/reset-password-confirm'
    })
        .then(({ data, error }) => {
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
            } else {
                alert('Check your email for a password reset link');
            }
        })
        .catch((error) => {
            console.error('Password reset error:', error.message);

            // Better error messages
            let errorMessage = 'Failed to send password reset email. Please try again.';

            if (error.message.includes('email rate limit')) {
                errorMessage = 'Too many password reset requests. Please wait a few minutes and try again.';
            } else if (error.message.includes('email_not_confirmed')) {
                errorMessage = 'Please confirm your email address first before resetting password.';
            } else if (error.message.includes('Over email send rate limits')) {
                errorMessage = 'Too many requests. Please wait 5 minutes before trying again.';
            } else if (error.message.includes('user_not_found')) {
                errorMessage = 'Email address not found. Please check the email and try again.';
            }

            alert('Error: ' + errorMessage);
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
        credentials: 'same-origin'  // Ensures cookies are sent with the request
    })
        .then(response => {
            console.log('Auth response status:', response.status);
            return response.json().then(data => ({ response, data }));
        })
        .then(({ response, data }) => {
            if (response.ok && data.success) {
                console.log('Backend authentication successful');
                // Track login via GA
                if (window.AbhiHubTracking) {
                    window.AbhiHubTracking.trackLogin('email', user?.email || '');
                }
                window.location.href = '/dashboard';
            } else {
                console.error('Backend authentication failed:', data.message);
                alert('Login failed: ' + (data.message || 'Unable to create session'));
            }
        })
        .catch(error => {
            console.error('Error during login:', error);
            alert('Error: ' + error.message);
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


