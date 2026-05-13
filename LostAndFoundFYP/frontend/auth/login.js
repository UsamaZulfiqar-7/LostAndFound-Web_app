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

    const name = document.getElementById("signupName").value.trim();
    const email = document.getElementById("signupEmail").value.trim();
    const password = document.getElementById("signupPassword").value.trim();
    const role = document.getElementById("signupRole").value;

    if (!role) {
      alert("Please select a role");
      return;
    }

    try {

      const res = await fetch("http://127.0.0.1:5000/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          name,
          email,
          password,
          role
        })
      });

      const data = await res.json();

      if (!res.ok) {
        alert(data.msg || "Signup failed");
        return;
      }

      alert(data.msg || "Signup successful");

      signupForm.reset();
      flipBox.classList.remove("flipped");

    }

    catch (err) {
      console.error(err);
      alert("Server not reachable");
    }

  });

}


// ================= LOGIN =================
const loginForm = document.getElementById("loginForm");

if (loginForm) {

  loginForm.addEventListener("submit", async (e) => {

    e.preventDefault();

    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value.trim();

    try {

      const res = await fetch("http://127.0.0.1:5000/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          email,
          password
        })
      });

      const data = await res.json();

      if (!res.ok) {
        alert(data.msg || "Login failed");
        return;
      }

      saveSession(data);

      redirectDashboard(data.role);

    }

    catch (err) {
      console.error(err);
      alert("Server not reachable");
    }

  });

}


// ================= GOOGLE LOGIN =================
async function handleGoogleLogin(response) {

  try {

    if (!response || !response.credential) {
      alert("Google credential missing");
      return;
    }

    const googleToken = response.credential;

    // ================= FIRST REQUEST =================
    const res = await fetch("http://127.0.0.1:5000/google-login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        token: googleToken
      })
    });

    const data = await res.json();

    // ================= NEW USER =================
    if (data.new_user === true) {

      let role = prompt("Enter role: finder or loser");

      if (!role) {
        alert("Role required");
        return;
      }

      role = role.toLowerCase().trim();

      if (role !== "finder" && role !== "loser") {
        alert("Invalid role");
        return;
      }

      // ================= CREATE ACCOUNT =================
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
        alert(finalData.msg || "Google signup failed");
        return;
      }

      saveSession(finalData);

      redirectDashboard(finalData.role);

    }

    // ================= EXISTING USER =================
    else {

      if (!res.ok) {
        alert(data.msg || "Google login failed");
        return;
      }

      saveSession(data);

      redirectDashboard(data.role);

    }

  }

  catch (err) {
    console.error("GOOGLE LOGIN ERROR:", err);
    alert("Google authentication failed");
  }

}


// ================= GLOBAL FUNCTION =================
window.handleGoogleLogin = handleGoogleLogin;


// ================= SAVE SESSION =================
function saveSession(data) {

  localStorage.setItem("token", data.token);
  localStorage.setItem("user_id", data.user_id);
  localStorage.setItem("role", data.role);
  localStorage.setItem("user_name", data.name);

}


// ================= DASHBOARD REDIRECT =================
function redirectDashboard(role) {

  if (!role) {
    alert("Role missing");
    return;
  }

  if (role === "admin") {

    window.location.href =
      "../dashboards/admin-dashboard.html";

  }

  else if (role === "finder") {

    window.location.href =
      "../dashboards/finder-dashboard.html";

  }

  else if (role === "loser") {

    window.location.href =
      "../dashboards/loser-dashboard.html";

  }

  else {

    alert("Invalid role");

  }

}


// ================= OPTIONAL GOOGLE PROMPT =================
function triggerGoogleLogin() {

  if (window.google && google.accounts) {
    google.accounts.id.prompt();
  }

}