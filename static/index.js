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
                window.location.hash = '';
                window.location.href = '/dashboard';
            } else {
                console.error('Backend login failed:', data.message);
                alert('Login failed: ' + (data.message || 'Unknown error'));
                window.location.hash = '';
            }
        } catch (error) {
            console.error('Error during OAuth callback:', error);
            alert('Error processing login: ' + error.message);
            window.location.hash = '';
        }
    }
}

// Run on page load if there's a hash (OAuth callback)
if (window.location.hash) {
    console.log('Hash detected on page load:', window.location.hash.substring(0, 50));
    handleOAuthCallback();
}

// Add meta tags and keywords in the HTML file for better indexing
document.head.insertAdjacentHTML('beforeend', `
  <meta name="description" content="AbhiHub - Share Notes, PYQ, Practicals, and Engineering (B.Tech) Notes with Friends">
  <meta name="keywords" content="AbhiHub, Notes Sharing, PYQ, Practicals, Engineering, B.Tech, Friends">
  <meta name="author" content="AbhiHub Team">
`);


/* === UI === */

/* == UI - Elements == */

const signOutButtonEl = document.getElementById("sign-out-btn")
if (signOutButtonEl) {
    signOutButtonEl.addEventListener("click", authSignOut)
}

const signInWithGoogleButtonEl = document.getElementById("sign-in-with-google-btn")

const emailInputEl = document.getElementById("email-input")
const passwordInputEl = document.getElementById("password-input")

const signInButtonEl = document.getElementById("sign-in-btn")
const createAccountButtonEl = document.getElementById("create-account-btn")



// const imgElement = document.getElementById("user-profile-picture")

// const greetElement = document.getElementById("greeting")

// const textareaEl = document.getElementById("post-input")
// const postButtonEl = document.getElementById("post-btn")

/* == UI - Event Listeners == */

if (signInWithGoogleButtonEl) {
    signInWithGoogleButtonEl.addEventListener("click", authSignInWithGoogle)
}

if (signInButtonEl) {
    signInButtonEl.addEventListener("click", authSignInWithEmail)
}

if (createAccountButtonEl) {
    createAccountButtonEl.addEventListener("click", authCreateAccountWithEmail)
}



/* === Main Code === */
// Listen to auth state changes
supabase.auth.onAuthStateChange((event, session) => {
    if (session) {
        // User is signed in
        const user = session.user;
        console.log("User signed in:", user);
        showLoggedInView(user)
    } else {
        showLoggedOutView()
    }
});


/* === Functions === */

/* = Functions - Supabase - Authentication = */

function authSignInWithGoogle() {
    supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
            redirectTo: window.location.origin // Redirect back to root, callback handler will catch it
        }
    })
        .then((result) => {
            if (result.error) {
                console.error('Error signing in with Google:', result.error.message);
            }
        })
        .catch((error) => {
            console.error(error.message)
        });
}
            // This gives you a Google Access Token. You can use it to access the Google API.
            const credential = GoogleAuthProvider.credentialFromResult(result);
            const token = credential.accessToken;
            // The signed-in user info.
            const user = result.user;
            user.getIdToken().then(function(idToken) {
                // The ID token you need
                console.log(idToken);
                // Send the ID token to your server, etc.
            });
            
            showLoggedInView(user)
            showProfilePicture(imgElement, user)
            showUserGreeting(greetElement, user)
            // IdP data available using getAdditionalUserInfo(result)
            // ...
        }).catch((error) => {
            // The AuthCredential type that was used.
            const credential = GoogleAuthProvider.credentialFromError(error);

            console.error(error.message)
        });

    
}

function authSignInWithEmail() {
    console.log("Sign in with email and password")

    const email = emailInputEl.value
    const password = passwordInputEl.value

    supabase.auth.signInWithPassword({
        email: email,
        password: password
    })
        .then(({ data, error }) => {
            if (error) {
                throw error;
            }
            
            const user = data.user;
            const session = data.session;
            console.log("User signed in: ", user)
            clearAuthFields()
            
            // Get the access token and log in
            const idToken = session.access_token;
            loginUser(user, idToken);
        })
        .catch((error) => {
            console.error("Error signing in: ", error.message)
        });
}

function authCreateAccountWithEmail() {
    const email = emailInputEl.value
    const password = passwordInputEl.value

    supabase.auth.signUp({
        email: email,
        password: password
    })
        .then(({ data, error }) => {
            if (error) {
                throw error;
            }
            
            const user = data.user;
            const session = data.session;
            console.log("User created: ", user)
            clearAuthFields()
            
            if (session) {
                const idToken = session.access_token;
                loginUser(user, idToken);
            }
        })
        .catch((error) => {
            console.error("Error creating user: ", error.message)
        });
}

function authSignOut() {
    console.log("User signed out")
    supabase.auth.signOut().then(() => {
        console.log("User signed out")
        window.location.href = '/login';
      }).catch((error) => {
        console.error(error.message)
      });
}

function loginUser(user, idToken) {
    fetch('/auth', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        credentials: 'same-origin'
    }).then(response => {
        if (response.ok) {
            window.location.href = '/dashboard';
        } else {
            console.error('Failed to login');
        }
    }).catch(error => {
        console.error('Error with Fetch operation: ', error);
    });
}


/* == Functions - UI Functions == */

function showLoggedOutView() {
    console.log("Show logged out view")
}

function showLoggedInView(user) {
    console.log("Show logged in view")
    console.log(user.id)
    window.location.href = '/dashboard';
}


function clearInputField(field) {
    if (field) {
        field.value = ""
    }
}

function clearAuthFields() {
	clearInputField(emailInputEl)
	clearInputField(passwordInputEl)
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(registration => {
        console.log('Service Worker registered with scope:', registration.scope);
      })
      .catch(error => {
        console.error('Service Worker registration failed:', error);
      });
  });
}


