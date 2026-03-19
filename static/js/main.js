let recorder;
let recorderStream;
let cameraStream;
let audioChunks = [];
let timerInterval;
let seconds = 0;

const THEME_STORAGE_KEY = "ai-medical-theme";

function getPasswordToggleIcon(isVisible) {
    if (isVisible) {
        return `
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M3 3L21 21" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                <path d="M10.58 10.58A2 2 0 0 0 13.41 13.41" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                <path d="M9.88 5.09A9.77 9.77 0 0 1 12 4.86C17 4.86 20.27 8.3 21.5 12C20.93 13.73 19.85 15.28 18.39 16.42" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                <path d="M14.12 18.91A9.77 9.77 0 0 1 12 19.14C7 19.14 3.73 15.7 2.5 12C3.05 10.31 4.08 8.79 5.48 7.66" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
        `;
    }

    return `
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M2.5 12C3.73 8.3 7 4.86 12 4.86C17 4.86 20.27 8.3 21.5 12C20.27 15.7 17 19.14 12 19.14C7 19.14 3.73 15.7 2.5 12Z" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
            <circle cx="12" cy="12" r="3" stroke-width="1.8"></circle>
        </svg>
    `;
}

function toggleSettings(event) {
    if (event) {
        event.stopPropagation();
    }

    const panel = document.getElementById("settings");
    if (!panel) {
        return;
    }

    const shouldOpen = !panel.classList.contains("open");
    closeFloatingPanels();
    if (shouldOpen) {
        panel.classList.add("open");
    }
}

function applyTheme(mode) {
    const isDark = mode === "dark";
    document.body.classList.toggle("dark", isDark);

    const themeSelect = document.getElementById("theme-select");
    if (themeSelect) {
        themeSelect.value = isDark ? "dark" : "light";
    }
}

function changeTheme(mode) {
    applyTheme(mode);
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
}

function previewImage(event) {
    const preview = document.getElementById("preview");
    const file = event.target.files[0];

    if (!preview) {
        return;
    }

    if (!file) {
        preview.removeAttribute("src");
        preview.classList.remove("is-visible");
        return;
    }

    const reader = new FileReader();
    reader.onload = function () {
        preview.src = reader.result;
        preview.classList.add("is-visible");
    };
    reader.readAsDataURL(file);
}

async function openCamera() {
    const video = document.getElementById("camera");
    if (!video) {
        return;
    }

    try {
        if (cameraStream) {
            cameraStream.getTracks().forEach((track) => track.stop());
        }

        cameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = cameraStream;
        video.style.display = "block";
    } catch (error) {
        alert("Camera access is not available right now.");
    }
}

function capturePhoto() {
    const video = document.getElementById("camera");
    const preview = document.getElementById("preview");
    const imageInput = document.querySelector('input[name="image"]');

    if (!video || !video.srcObject) {
        alert("Open the camera before capturing a photo.");
        return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);

    const dataURL = canvas.toDataURL("image/jpeg");
    if (preview) {
        preview.src = dataURL;
        preview.classList.add("is-visible");
    }

    fetch(dataURL)
        .then((response) => response.blob())
        .then((blob) => {
            const imageFile = new File([blob], "camera-capture.jpg", { type: "image/jpeg" });
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(imageFile);

            if (imageInput) {
                imageInput.files = dataTransfer.files;
            }
        });

    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
    }

    video.srcObject = null;
    video.style.display = "none";
}

async function startRec() {
    try {
        recorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(recorderStream);
        recorder.start();

        audioChunks = [];
        seconds = 0;

        const timer = document.getElementById("timer");
        if (timer) {
            timer.textContent = "00:00";
        }

        timerInterval = window.setInterval(() => {
            seconds += 1;
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;

            if (timer) {
                timer.textContent = `${minutes.toString().padStart(2, "0")}:${remainingSeconds
                    .toString()
                    .padStart(2, "0")}`;
            }
        }, 1000);

        recorder.ondataavailable = (event) => audioChunks.push(event.data);
    } catch (error) {
        alert("Microphone access is not available right now.");
    }
}

function stopRec() {
    if (!recorder || recorder.state === "inactive") {
        alert("Recording has not started.");
        return;
    }

    recorder.stop();
    window.clearInterval(timerInterval);

    recorder.onstop = () => {
        const blob = new Blob(audioChunks, { type: recorder.mimeType || "audio/webm" });
        const extension = blob.type.includes("mp4") ? "mp4" : "webm";
        const audioFile = new File([blob], `recording.${extension}`, { type: blob.type });
        const dataTransfer = new DataTransfer();

        dataTransfer.items.add(audioFile);

        const audioInput = document.getElementById("audioFile");
        if (audioInput) {
            audioInput.files = dataTransfer.files;
        }

        if (recorderStream) {
            recorderStream.getTracks().forEach((track) => track.stop());
            recorderStream = null;
        }
    };
}

function resizeTextarea(textarea) {
    const maxHeight = Number(textarea.dataset.maxHeight || 220);
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
}

function wireAutoExpand() {
    document.querySelectorAll("textarea.auto-expand").forEach((textarea) => {
        resizeTextarea(textarea);
        textarea.addEventListener("input", () => resizeTextarea(textarea));
    });
}

function wirePasswordToggles() {
    document.querySelectorAll('input[type="password"]').forEach((input) => {
        if (input.dataset.passwordToggleReady === "true") {
            return;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "password-field";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const toggleButton = document.createElement("button");
        toggleButton.type = "button";
        toggleButton.className = "password-toggle";
        toggleButton.setAttribute("aria-label", "Show password");
        toggleButton.setAttribute("title", "Show password");
        toggleButton.innerHTML = getPasswordToggleIcon(false);

        toggleButton.addEventListener("click", function () {
            const isVisible = input.type === "text";
            input.type = isVisible ? "password" : "text";
            toggleButton.setAttribute(
                "aria-label",
                isVisible ? "Show password" : "Hide password"
            );
            toggleButton.setAttribute(
                "title",
                isVisible ? "Show password" : "Hide password"
            );
            toggleButton.innerHTML = getPasswordToggleIcon(!isVisible);
        });

        wrapper.appendChild(toggleButton);
        input.dataset.passwordToggleReady = "true";
    });
}

function ensureLiveErrorElement(input) {
    if (input.dataset.liveErrorId) {
        return document.getElementById(input.dataset.liveErrorId);
    }

    const fieldKey = input.id || input.name || `field-${Math.random().toString(36).slice(2, 8)}`;
    const errorId = `${fieldKey}-live-error`;
    let errorElement = document.getElementById(errorId);

    if (!errorElement) {
        errorElement = document.createElement("div");
        errorElement.id = errorId;
        errorElement.className = "error live-error";
        errorElement.hidden = true;
        errorElement.setAttribute("aria-live", "polite");
        input.insertAdjacentElement("afterend", errorElement);
    }

    input.dataset.liveErrorId = errorId;
    input.setAttribute("aria-describedby", errorId);
    return errorElement;
}

function setLiveFieldState(input, isValid, message) {
    const errorElement = ensureLiveErrorElement(input);

    input.classList.toggle("input-invalid", !isValid);
    input.setAttribute("aria-invalid", isValid ? "false" : "true");

    if (isValid) {
        input.setCustomValidity("");
        errorElement.hidden = true;
        errorElement.textContent = "";
        return true;
    }

    input.setCustomValidity(message);
    errorElement.hidden = false;
    errorElement.textContent = message;
    return false;
}

function validateEmailField(input, force = false) {
    const value = input.value.trim();
    const touched = force || input.dataset.validationTouched === "true";

    if (!value) {
        return touched
            ? setLiveFieldState(input, false, "Email ID is required.")
            : setLiveFieldState(input, true, "");
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    if (!emailPattern.test(value)) {
        return setLiveFieldState(input, false, "Enter a valid email ID.");
    }

    return setLiveFieldState(input, true, "");
}

function validateMobileField(input, force = false) {
    const value = input.value.trim();
    const touched = force || input.dataset.validationTouched === "true";
    const minDigits = Number(input.dataset.minDigits || 10);
    const maxDigits = Number(input.dataset.maxDigits || 15);

    if (!value) {
        return touched
            ? setLiveFieldState(input, false, "Mobile number is required.")
            : setLiveFieldState(input, true, "");
    }

    if (!/^\d+$/.test(value)) {
        return setLiveFieldState(
            input,
            false,
            "Use digits only in the mobile number."
        );
    }

    if (value.length < minDigits || value.length > maxDigits) {
        return setLiveFieldState(
            input,
            false,
            `Enter a valid mobile number with ${minDigits} to ${maxDigits} digits.`
        );
    }

    return setLiveFieldState(input, true, "");
}

function validateLiveField(input, force = false) {
    const validationType = input.dataset.liveValidate;
    if (validationType === "email") {
        return validateEmailField(input, force);
    }

    if (validationType === "mobile") {
        return validateMobileField(input, force);
    }

    return true;
}

function wireLiveValidation() {
    const liveFields = document.querySelectorAll("[data-live-validate]");
    if (!liveFields.length) {
        return;
    }

    liveFields.forEach((input) => {
        if (input.dataset.liveValidationReady === "true") {
            return;
        }

        ensureLiveErrorElement(input);
        input.addEventListener("input", function () {
            input.dataset.validationTouched = "true";
            validateLiveField(input);
        });

        input.addEventListener("blur", function () {
            input.dataset.validationTouched = "true";
            validateLiveField(input, true);
        });

        input.dataset.liveValidationReady = "true";
    });

    document.querySelectorAll("form").forEach((form) => {
        if (form.dataset.liveValidationBound === "true") {
            return;
        }

        const fields = form.querySelectorAll("[data-live-validate]");
        if (!fields.length) {
            return;
        }

        form.addEventListener("submit", function (event) {
            let firstInvalidField = null;

            fields.forEach((field) => {
                field.dataset.validationTouched = "true";
                const isValid = validateLiveField(field, true);
                if (!isValid && !firstInvalidField) {
                    firstInvalidField = field;
                }
            });

            if (firstInvalidField) {
                event.preventDefault();
                firstInvalidField.focus();
            }
        });

        form.dataset.liveValidationBound = "true";
    });
}

function wireFormLoadingStates() {
    const mainForm = document.getElementById("mainForm");
    if (mainForm) {
        mainForm.addEventListener("submit", () => {
            const button = document.getElementById("analyzeBtn");
            if (button) {
                button.innerHTML = "<span class='loader'></span>Analyzing...";
                button.disabled = true;
            }
        });
    }

    const chatForm = document.querySelector(".chat-form");
    if (chatForm) {
        chatForm.addEventListener("submit", () => {
            const submitButton = chatForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.innerHTML = "<span class='loader'></span>Sending...";
                submitButton.disabled = true;
            }

            const chatBox = document.getElementById("chatBox");
            if (chatBox) {
                const loader = document.createElement("div");
                loader.className = "message assistant";
                loader.innerHTML =
                    "<div class='meta'>Assistant</div><div class='text'>Preparing a response...</div>";
                chatBox.appendChild(loader);
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        });
    }
}

function closeFloatingPanels() {
    const settingsPanel = document.getElementById("settings");
    if (settingsPanel) {
        settingsPanel.classList.remove("open");
    }

    const navMenu = document.getElementById("nav-menu");
    if (navMenu) {
        navMenu.classList.remove("open");
    }

    document.querySelectorAll(".menu-shell[open]").forEach((menuShell) => {
        menuShell.removeAttribute("open");
    });

    const navToggle = document.querySelector(".menu-shell .menu-toggle");
    if (navToggle && navToggle.hasAttribute("aria-expanded")) {
        navToggle.setAttribute("aria-expanded", "false");
    }
}

document.addEventListener("DOMContentLoaded", function () {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY) || "light";
    applyTheme(storedTheme);
    wireAutoExpand();
    wirePasswordToggles();
    wireLiveValidation();
    wireFormLoadingStates();

    const languageSelect = document.getElementById("language-select");
    if (languageSelect && !document.getElementById("mainForm")) {
        languageSelect.disabled = true;
        languageSelect.title = "Response language is available on the clinical intake page.";
    }

    const settingsPanel = document.getElementById("settings");
    if (settingsPanel) {
        settingsPanel.addEventListener("click", function (event) {
            event.stopPropagation();
        });
    }

    const navMenu = document.getElementById("nav-menu");
    if (navMenu) {
        navMenu.addEventListener("click", function (event) {
            event.stopPropagation();
        });
    }

    document.querySelectorAll(".menu-shell").forEach((menuShell) => {
        menuShell.addEventListener("toggle", function () {
            const toggle = menuShell.querySelector(".menu-toggle");
            if (toggle) {
                toggle.setAttribute("aria-expanded", menuShell.open ? "true" : "false");
            }
        });

        menuShell.addEventListener("click", function (event) {
            event.stopPropagation();
        });
    });

    const chatBox = document.getElementById("chatBox");
    if (chatBox) {
        chatBox.scrollTop = chatBox.scrollHeight;
    }
});

window.addEventListener("click", function () {
    closeFloatingPanels();
});
