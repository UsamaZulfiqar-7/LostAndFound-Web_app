// ================= FLIP LOGIN / SIGNUP =================
const flipBox = document.getElementById("flipBox");
const openSignupBtn = document.getElementById("openSignup");
const openLoginBtn = document.getElementById("openLogin");

if (openSignupBtn) {
  openSignupBtn.onclick = () => flipBox.classList.add("flipped");
}
if (openLoginBtn) {
  openLoginBtn.onclick = () => flipBox.classList.remove("flipped");
}


// ================= SIGNUP =================
const signupForm = document.getElementById("signupForm");

if (signupForm) {
  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const name = document.getElementById("signupName").value;
    const email = document.getElementById("signupEmail").value;
    const password = document.getElementById("signupPassword").value;
    const role = document.getElementById("signupRole").value;

    if (!role) {
      alert("Please select a role");
      return;
    }

    try {
      const res = await fetch("http://127.0.0.1:5000/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password, role })
      });

      const data = await res.json();
      alert(data.msg);

      if (res.status === 201) {
        flipBox.classList.remove("flipped");
        signupForm.reset();
      }

    } catch (err) {
      alert("Server not reachable");
    }
  });
}


// ================= LOGIN =================
const loginForm = document.getElementById("loginForm");

if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;

    try {
      const res = await fetch("http://127.0.0.1:5000/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });

      const data = await res.json();

      if (res.status !== 200) {
        alert(data.msg);
        return;
      }

      // ✅ SAVE SESSION
      localStorage.setItem("token", data.token);
      localStorage.setItem("user_id", data.user_id);
      localStorage.setItem("role", data.role);
      localStorage.setItem("user_name", data.name);

      redirectDashboard(data.role);

    } catch (err) {
      alert("Server not reachable");
    }
  });
}


// ================= GOOGLE LOGIN (FIXED) =================
async function handleGoogleLogin(response) {
  const googleToken = response.credential;

  if (!googleToken) {
    alert("Google token not received");
    return;
  }

  try {
    // 🔥 STEP 1: CALL BACKEND
    const res = await fetch("http://127.0.0.1:5000/google-login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token: googleToken })
    });

    const data = await res.json();

    // =============================
    // 🆕 NEW USER → ROLE SELECT
    // =============================
    if (data.new_user) {

      // 👉 simple version (prompt)
      let role = prompt("Select role: finder or loser");

      if (!role || (role !== "finder" && role !== "loser")) {
        alert("Invalid role selected");
        return;
      }

      // 🔥 CALL AGAIN WITH ROLE
      const res2 = await fetch("http://127.0.0.1:5000/google-login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          token: googleToken,
          role: role
        })
      });

      const finalData = await res2.json();

      if (!res2.ok) {
        alert(finalData.msg || "Error creating account");
        return;
      }

      saveAndRedirect(finalData);

    } else {
      // =============================
      // ✅ EXISTING USER
      // =============================
      saveAndRedirect(data);
    }

  } catch (err) {
    console.error(err);
    alert("Google login failed");
  }
}

// 🔥 VERY IMPORTANT (GLOBAL)
window.handleGoogleLogin = handleGoogleLogin;


// ================= DASHBOARD REDIRECT =================
function redirectDashboard(role) {
  if (role === "admin") {
    window.location.replace("../dashboards/admin-dashboard.html");
  }
  else if (role === "finder") {
    window.location.replace("../dashboards/finder-dashboard.html");
  }
  else {
    window.location.replace("../dashboards/loser-dashboard.html");
  }
}
function triggerGoogleLogin() {
  google.accounts.id.prompt(); 
}

function saveAndRedirect(data) {
  localStorage.setItem("token", data.token);
  localStorage.setItem("user_id", data.user_id);
  localStorage.setItem("role", data.role);
  localStorage.setItem("user_name", data.name);

  redirectDashboard(data.role);
}
