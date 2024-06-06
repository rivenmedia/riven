// We can only access api from server-side so this needs to be made into a server route

export const GET = async ({ fetch, params }) => {
	const id: number = Number(params.id);
	console.log(`Fetching extended data of item ${id} from backend`);

	async function getExtendedData() {
		try {
			const res = await fetch(`http://127.0.0.1:8080/items/extended/${id}`);
			if (res.ok) {
				return await res.json();
			}
			return {
				status: res.status,
				statusText: res.statusText
			};
		} catch (e) {
			console.error(e);
			return {
				status: 503,
				statusText: 'Unable to fetch extended data. API is down.'
			};
		}
	}

	const data = await getExtendedData();

	return new Response(JSON.stringify(data), {
		headers: {
			'Content-Type': 'application/json'
		}
	});
};
