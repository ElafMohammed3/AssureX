document.addEventListener('DOMContentLoaded', () => {
  
    setupPasswordToggle('password', 'togglePassword');
    setupPasswordToggle('confirm_password', 'toggleConfirmPassword');

    function setupPasswordToggle(inputId, toggleId) {
        const input = document.getElementById(inputId);
        const toggle = document.getElementById(toggleId);

        if (input && toggle) {
            toggle.addEventListener('click', () => {
                const isPassword = input.getAttribute('type') === 'password';
                input.setAttribute('type', isPassword ? 'text' : 'password');
                toggle.classList.toggle('fa-eye');
                toggle.classList.toggle('fa-eye-slash');
            });
        }
    }

   
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', (e) => {
            let isValid = true;
            clearErrors();

            const fullName = document.getElementById('full_name');
            const email = document.getElementById('email');
            const phone = document.getElementById('phone');
            const password = document.getElementById('password');
            const confirmPassword = document.getElementById('confirm_password');
            const terms = document.getElementById('terms');
            const alertBox = document.getElementById('alert-box');

            if (!fullName.value.trim()) {
                showError('full_name-error', 'Full Name is required');
                isValid = false;
            }

            if (!email.value.trim()) {
                showError('email-error', 'Email address is required');
                isValid = false;
            }

            if (!phone.value.trim()) {
                showError('phone-error', 'Phone number is required');
                isValid = false;
            }

            if (!password.value) {
                showError('password-error', 'Password is required');
                isValid = false;
            } else if (password.value.length < 6) {
                showError('password-error', 'Password must be at least 6 characters');
                isValid = false;
            }

            if (confirmPassword.value !== password.value) {
                showError('confirm_password-error', 'Passwords do not match');
                isValid = false;
            }

            if (!terms.checked) {
                showError('terms-error', 'You must accept the terms and conditions');
                isValid = false;
            }

            if (!isValid) {
                e.preventDefault();
                if (alertBox) alertBox.classList.remove('hidden');
            }
        });
    }

    function showError(elementId, message) {
        const el = document.getElementById(elementId);
        if (el) el.innerText = message;
    }

    function clearErrors() {
        document.querySelectorAll('.error-msg').forEach(el => el.innerText = '');
        const alertBox = document.getElementById('alert-box');
        if (alertBox) alertBox.classList.add('hidden');
    }
});