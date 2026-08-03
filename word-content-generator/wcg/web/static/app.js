const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function setBusy(busy, message) {
  $("suggest-btn").disabled = busy;
  $("topic").disabled = busy;
  $("variants").classList.toggle("busy", busy);
  if (message === undefined) return;
  const status = $("generate-status");
  status.textContent = "";
  if (busy) {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    status.appendChild(spinner);
  }
  status.appendChild(document.createTextNode(message || ""));
}

$("propose-form").onsubmit = async (event) => {
  event.preventDefault();
  const topic = $("topic").value.trim();
  if (!topic) return;
  setBusy(true, "Asking the model for suggestions...");
  $("variants").innerHTML = "";
  try {
    const data = await api("/api/propose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    renderVariants(data.variants);
    $("generate-status").textContent = data.variants.length
      ? "Pick one to add it to the pool:"
      : "No valid suggestions returned - try again.";
  } catch (error) {
    $("generate-status").textContent = "Error: " + error.message;
  } finally {
    setBusy(false, undefined);
  }
};

function renderVariants(variants) {
  const container = $("variants");
  container.innerHTML = "";
  variants.forEach((variant) => {
    const card = document.createElement("div");
    card.className = "card";
    const title = document.createElement("h3");
    title.textContent = variant.descriptor;
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `In game: ${variant.name} · difficulty: ${variant.difficulty}`;
    const words = document.createElement("p");
    words.className = "words";
    words.textContent = variant.words.join(" · ");
    const button = document.createElement("button");
    button.textContent = "Pick this one";
    button.onclick = () => select(variant);
    card.append(title, meta, words, button);
    container.appendChild(card);
  });
}

async function select(variant) {
  setBusy(true, "Saving...");
  const variantButtons = $("variants").querySelectorAll("button");
  variantButtons.forEach((button) => { button.disabled = true; });
  try {
    const data = await api("/api/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variant }),
    });
    const warnings = data.warnings.length
      ? ` (warnings: ${data.warnings.join("; ")})` : "";
    $("generate-status").textContent =
      `Saved "${data.category.names.en}" as ${data.category.id}` +
      ` - translating in background${warnings}`;
    $("variants").innerHTML = "";
    $("topic").value = "";
  } catch (error) {
    $("generate-status").textContent = "Error: " + error.message;
  } finally {
    setBusy(false, undefined);
    variantButtons.forEach((button) => { button.disabled = false; });
  }
}
