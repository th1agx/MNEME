// Guarda o endereço do site e a chave de leitura só neste navegador.
const site = document.getElementById("site"), chave = document.getElementById("chave"), estado = document.getElementById("estado");
chrome.storage.local.get(["site", "chave"]).then((c) => { site.value = c.site || ""; chave.value = c.chave || ""; });
document.getElementById("salvar").onclick = async () => {
  await chrome.storage.local.set({ site: site.value.trim(), chave: chave.value.trim() });
  estado.textContent = "salvo";
  estado.className = "ok";
};
