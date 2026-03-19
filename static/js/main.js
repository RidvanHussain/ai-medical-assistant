let recorder;
let recorderStream;
let cameraStream;
let audioChunks = [];
let timerInterval;
let seconds = 0;

const THEME_STORAGE_KEY = "ai-medical-theme";

function toggleSettings(event) {
    if (event) {
        event.stopPropagation();
    }

    const panel = document.getElementById("settings");
    if (!panel) {
        return;
    }

    panel.classList.toggle("open");
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

function toggleUserMenu(event) {
    event.stopPropagation();
    const dropdown = event.currentTarget;
    dropdown.classList.toggle("active");
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

    document.querySelectorAll(".user-dropdown.active").forEach((dropdown) => {
        dropdown.classList.remove("active");
    });
}

document.addEventListener("DOMContentLoaded", function () {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY) || "light";
    applyTheme(storedTheme);
    wireAutoExpand();
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

    const chatBox = document.getElementById("chatBox");
    if (chatBox) {
        chatBox.scrollTop = chatBox.scrollHeight;
    }
});

window.addEventListener("click", function () {
    closeFloatingPanels();
});
