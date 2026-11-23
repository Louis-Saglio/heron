const PRINT_BUFFER_BYTES = 16384;
const BYTES_PER_CHARACTER = 4;
const PART_CHARACTERS = Math.floor(PRINT_BUFFER_BYTES / BYTES_PER_CHARACTER) - 64;

export function line(player, tag, data)
{
	const text = JSON.stringify(Object.assign({ "p": player }, data));
	if (text.length <= PART_CHARACTERS)
	{
		print("[" + tag + "] " + text + "\n");
		return;
	}
	const parts = Math.ceil(text.length / PART_CHARACTERS);
	for (let part = 0; part < parts; ++part)
		print("[" + tag + " " + player + " " + (part + 1) + "/" + parts + "] " + text.slice(part * PART_CHARACTERS, (part + 1) * PART_CHARACTERS) + "\n");
}
