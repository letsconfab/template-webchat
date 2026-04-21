// Debug script to check authentication state
// Run this in browser console after logging in

function debugAuth() {
    console.log('=== Authentication Debug ===');
    
    // Check localStorage
    const token = localStorage.getItem('token');
    console.log('Token in localStorage:', token ? '✅ Found' : '❌ Missing');
    if (token) {
        console.log('Token length:', token.length);
        console.log('Token preview:', token.substring(0, 50) + '...');
    }
    
    // Check current user in AuthContext (if available)
    if (window.__AUTH_CONTEXT__) {
        console.log('AuthContext user:', window.__AUTH_CONTEXT__.user);
        console.log('AuthContext token:', window.__AUTH_CONTEXT__.token ? '✅ Set' : '❌ Missing');
    }
    
    // Test API call with authentication
    fetch('/api/auth/me', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
    .then(response => {
        if (response.ok) {
            console.log('✅ API call with token successful');
            return response.json();
        } else {
            console.log('❌ API call failed:', response.status);
            throw new Error('API call failed');
        }
    })
    .then(data => {
        console.log('✅ User data:', data);
    })
    .catch(error => {
        console.error('❌ API call error:', error);
    });
    
    // Test axios interceptor (if available)
    if (window.__API_INSTANCE__) {
        console.log('Axios instance found');
        console.log('Axios default headers:', window.__API_INSTANCE__.defaults.headers.common);
    }
}

// Auto-expose the function
window.debugAuth = debugAuth;
console.log('Debug function loaded. Run debugAuth() in console to check authentication state.');
