(() => {
    const form = document.getElementById('employeeForm');

    if (!form) {
        return;
    }

    const submitButton = document.getElementById('submitButton');
    const fields = {
        name: document.getElementById('name'),
        email: document.getElementById('email'),
        phone: document.getElementById('phone'),
        department: document.getElementById('department'),
        salary: document.getElementById('salary'),
        joining_date: document.getElementById('joining_date')
    };
    const today = new Date().toISOString().split('T')[0];

    fields.joining_date.max = today;

    function setError(fieldName, message) {
        const field = fields[fieldName];
        const error = document.getElementById(`${fieldName}Error`);

        field.classList.toggle('invalid', Boolean(message));
        error.textContent = message;
    }

    function validateField(fieldName) {
        const value = fields[fieldName].value.trim();
        let message = '';

        if (fieldName === 'name') {
            const letters = value.replace(/[^A-Za-z]/g, '');
            if (!value) {
                message = 'Name is required.';
            } else if (!/^[A-Za-z ]+$/.test(value) || letters.length < 3) {
                message = 'Use at least 3 letters and alphabets only.';
            }
        }

        if (fieldName === 'email') {
            const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!value) {
                message = 'Email is required.';
            } else if (!emailPattern.test(value)) {
                message = 'Enter a valid email with @ and .';
            }
        }

        if (fieldName === 'phone' && !/^\d{10}$/.test(value)) {
            message = 'Phone must contain exactly 10 digits.';
        }

        if (fieldName === 'department' && !value) {
            message = 'Department is required.';
        }

        if (fieldName === 'salary' && (!value || Number(value) <= 0)) {
            message = 'Salary must be greater than 0.';
        }

        if (fieldName === 'joining_date') {
            if (!value) {
                message = 'Joining date is required.';
            } else if (value > today) {
                message = 'Joining date cannot be in the future.';
            }
        }

        setError(fieldName, message);
        return !message;
    }

    function validateForm() {
        const valid = Object.keys(fields).every(validateField);
        submitButton.disabled = !valid;
        return valid;
    }

    Object.values(fields).forEach((field) => {
        field.addEventListener('input', validateForm);
        field.addEventListener('change', validateForm);
    });

    form.addEventListener('submit', (event) => {
        if (!validateForm()) {
            event.preventDefault();
            return;
        }

        const savedEmployees = JSON.parse(
            localStorage.getItem('employeeDashboardData') || '[]'
        );
        savedEmployees.push({
            id: Date.now(),
            name: fields.name.value.trim(),
            email: fields.email.value.trim(),
            phone: fields.phone.value.trim(),
            department: fields.department.value.trim(),
            designation: document.getElementById('designation').value.trim(),
            salary: Number(fields.salary.value),
            joining_date: fields.joining_date.value,
            skills: document.getElementById('skills').value
                .split(',')
                .map((skill) => skill.trim())
                .filter(Boolean),
            status: 'Present'
        });
        localStorage.setItem(
            'employeeDashboardData',
            JSON.stringify(savedEmployees)
        );
    });

    validateForm();
})();
