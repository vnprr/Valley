import { expect, test, type Page } from "@playwright/test";

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1440) < 1100;

async function newMeeting(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByTitle("Nowe spotkanie").click();
  await expect(page.locator(".title-input")).toHaveValue("Nowe spotkanie");
  await expect(page.locator(".card")).toHaveCount(0);
}

async function say(page: Page, text: string) {
  await page.getByLabel("Opisz spotkanie").fill(text);
  await page.getByLabel("Wyślij").click();
  await expect(page.locator(".reply")).toBeVisible();
  await expect(page.getByLabel("Wyślij").locator(".spin")).toHaveCount(0);
  // Z E2E_AI=1 wymagamy, żeby odpowiedział model, a nie zapasowy parser reguł.
  if (process.env.E2E_AI === "1") await expect(page.locator(".reply")).toHaveAttribute("data-source", "ai");
}

const card = (page: Page, name: string) => page.locator(`.card[data-name="${name}"]`);
const names = (page: Page) => page.locator(".card .card-name");

async function openCard(page: Page, name: string) {
  if (isMobile(page)) await page.locator(".dock-tabs button").first().click();
  const c = card(page, name);
  if ((await c.getAttribute("class"))?.includes("is-open")) return c;
  await c.locator(".card-head").click();
  return c;
}

test("polecenia tekstowe dodają, zmieniają i usuwają osoby — także po przeładowaniu", async ({ page }) => {
  await newMeeting(page);

  await say(page, "Dodaj Olę i Pawła");
  await expect(names(page)).toHaveText(["Ola", "Paweł"]);

  await say(page, "Będziemy we czwórkę");
  await expect(names(page)).toHaveCount(4);

  await say(page, "Ola jedzie rowerem");
  await expect(card(page, "Ola").getByLabel("rower")).toBeVisible();

  await say(page, "Zmień Oli transport na auto i limit na 25 minut");
  let ola = await openCard(page, "Ola");
  await expect(ola.locator(".segmented .is-on")).toContainText("samochód");
  await expect(ola.locator('input[type="number"]')).toHaveValue("25");

  await say(page, "Zmień imię Oli na Aleksandra");
  await expect(card(page, "Aleksandra")).toBeVisible();
  await expect(card(page, "Ola")).toHaveCount(0);

  await say(page, "Nie usuwaj Aleksandry");
  await expect(names(page)).toHaveCount(4);

  await say(page, "Usuń Pawła i dodaj Kasię");
  await expect(card(page, "Paweł")).toHaveCount(0);
  await expect(card(page, "Kasia")).toBeVisible();

  // Karty odzwierciedlają ZAPISANY stan: po przeładowaniu wszystko zostaje.
  await page.reload();
  await expect(card(page, "Aleksandra")).toBeVisible();
  await expect(card(page, "Kasia")).toBeVisible();
  await expect(card(page, "Paweł")).toHaveCount(0);
  ola = await openCard(page, "Aleksandra");
  await expect(ola.locator('input[type="number"]')).toHaveValue("25");
});

test("niejednoznaczne zmniejszenie grupy pyta zamiast usuwać", async ({ page }) => {
  await newMeeting(page);
  await say(page, "Dodaj Olę, Adama i Kasię");
  await expect(names(page)).toHaveCount(3);
  await say(page, "Będziemy we dwoje");
  await expect(page.locator(".reply-question")).toBeVisible();
  await expect(names(page)).toHaveCount(3);
});

test("lokalizacja słowna staje się propozycją do zatwierdzenia", async ({ page }) => {
  await newMeeting(page);
  await say(page, "Dodaj Kasię");
  await say(page, "Kasia startuje z Mokotowa");
  const kasia = card(page, "Kasia");
  await expect(kasia.locator(".proposal")).toContainText("Mokotów");
  await expect(kasia.locator(".chip")).toHaveText("Zatwierdź start");
  await kasia.getByTitle("Zatwierdź start").click();
  await expect(kasia.locator(".proposal")).toHaveCount(0);
  await expect(kasia.locator(".chip")).toHaveText("Wybierz transport");
});

test("ręczne karty + starty na mapie + obliczenie tras", async ({ page }) => {
  await newMeeting(page);
  await say(page, "Ola jedzie rowerem, a Adam idzie pieszo");
  await expect(names(page)).toHaveText(["Ola", "Adam"]);

  const box = (await page.locator(".maplibregl-canvas").boundingBox())!;
  const mobile = isMobile(page);
  const points: [string, number, number][] = mobile
    ? [["Ola", 0.3, 0.25], ["Adam", 0.7, 0.3]]
    : [["Ola", 0.4, 0.4], ["Adam", 0.6, 0.45]];
  for (const [name, fx, fy] of points) {
    const c = await openCard(page, name);
    await c.getByRole("button", { name: "Ustaw start" }).click();
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
    await page.waitForTimeout(400);
    // po ręcznym wyborze tryb wyboru się kończy
    await expect(page.locator(".picking-banner")).toHaveCount(0);
  }
  await expect(page.locator(".pin:not(.is-proposal)")).toHaveCount(2);
  if (mobile) await page.locator(".dock-tabs button").first().click();
  await page.locator(".cta").click();
  await expect(page.locator(".rec")).toHaveCount(3, { timeout: 60_000 });

  if (mobile) await page.locator(".dock-tabs button").first().click();
  await expect(card(page, "Ola").locator(".chip")).toHaveText(/Czas: \d+ min/);

  // zmiana transportu -> wynik nieaktualny, karta nie pokazuje starego czasu
  await say(page, "Adam jednak jedzie rowerem");
  await expect(card(page, "Adam").locator(".chip")).toHaveText("Przelicz");
});

test("demo offline: VALLEY i suwak α bez ponownego routingu", async ({ page }) => {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("select").selectOption({ label: "Demo · kawa w 4 osoby" });
  if (isMobile(page)) await page.locator(".dock-tabs button").nth(1).click();
  await expect(page.locator(".rec")).toHaveCount(3);
  await page.getByRole("button", { name: "VALLEY" }).click();
  await expect(page.locator(".legend")).toBeVisible();
  await page.locator('input[type="range"]').fill("1");
  await expect(page.locator(".alpha-labels b")).toHaveText("α 1.00");
  await expect(page.locator(".summary")).toContainText("sprawiedliwość");
});
