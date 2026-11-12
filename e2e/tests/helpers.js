// Shared test helpers.

// The sidebar is an off-canvas drawer on phones: open it first when the menu button is visible.
export async function logout(page) {
  const menu = page.getByRole('button', { name: 'Open menu' })
  if (await menu.isVisible()) await menu.click()
  await page.getByTitle('Log out').click()
}
