/* Butoni 👁️ te çdo fushë fjalëkalimi: shfaq / fsheh fjalëkalimin. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('input[type="password"]').forEach(function (fusha) {
    var mbeshtjellesi = document.createElement('span');
    mbeshtjellesi.className = 'fjalekalimi-syri';
    fusha.parentNode.insertBefore(mbeshtjellesi, fusha);
    mbeshtjellesi.appendChild(fusha);
    var butoni = document.createElement('button');
    butoni.type = 'button';
    butoni.className = 'syri-buton';
    butoni.setAttribute('aria-label', 'Shfaq fjalëkalimin');
    butoni.textContent = '👁️';
    butoni.addEventListener('click', function () {
      var shfaqur = fusha.type === 'text';
      fusha.type = shfaqur ? 'password' : 'text';
      butoni.textContent = shfaqur ? '👁️' : '🙈';
      butoni.setAttribute('aria-label', shfaqur ? 'Shfaq fjalëkalimin' : 'Fshih fjalëkalimin');
      fusha.focus();
    });
    mbeshtjellesi.appendChild(butoni);
  });
});
