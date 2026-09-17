  function closeNotification() {
    const popup = document.getElementById('notificationPopup');
    if (popup) {
      popup.classList.remove('show');
      setTimeout(() => popup.style.display = 'none', 300);
    }
  }

  function toggleShareOptions() {
    const options = document.getElementById('shareOptions');
    options.classList.toggle('show');
  }

  function shareApp(platform) {
    const text = "Check out AbhiHub - The best place for engineering resources! 📚🚀";
    const url = "https://abhihub.in";

    if (platform === 'whatsapp') {
      window.open(`https://wa.me/?text=${encodeURIComponent(text + ' ' + url)}`);
    } else if (platform === 'twitter') {
      window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`);
    }
  }

  function copyLink() {
    navigator.clipboard.writeText("https://abhihub.in");
    alert("Link copied to clipboard!");
  }