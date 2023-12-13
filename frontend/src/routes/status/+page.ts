import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const getItems = async () => {
		const res = await fetch('http://%hostip%:8080/items/');
		if (res.ok) {
			return await res.json();
		}
		return null;
	};

    const getStates = async () => {
        const res = await fetch('http://%hostip%:8080/items/states');
        if (res.ok) {
            return await res.json();
        }
        return null;
    }

	return {
        streamed: {
            items: getItems(),
        },
        states: getStates()
	};
};
