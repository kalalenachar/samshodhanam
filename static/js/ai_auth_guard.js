/**
 * Authentication Guard for Samshodhana Mandiram
 */

function isUserLoggedIn() {
    const token = localStorage.getItem('user_token');
    const userStr = localStorage.getItem('user_profile');
    if (token && userStr) {
        try {
            const user = JSON.parse(userStr);
            if (user && (user.id || user.email)) return true;
        } catch (e) {}
    }
    return false;
}

function checkAiAccess(url) {
    window.location.href = url;
}

function openAiAuthModal() {}
function closeAiAuthModal() {}
