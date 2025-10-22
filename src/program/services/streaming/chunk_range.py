class ChunkRange:
    """
    Represents a range of data to be fetched from a media stream,
    including calculations for chunk boundaries and required bytes.
    """

    def __init__(
        self,
        position: int,
        *,
        chunk_size: int,
        header_size: int,
        size: int,
    ) -> None:
        self.request_range = (position, position + size - 1)
        self.size = size
        self.chunk_size = chunk_size
        self.header_size = header_size

        # Calculate position relative to content start (excluding header)
        content_position = max(0, position - header_size)

        # Calculate first chunk range based on content position
        first_chunk_index = content_position // chunk_size

        first_chunk_start = min(
            position,
            header_size + (first_chunk_index * chunk_size),
        )
        first_chunk_end = first_chunk_start + chunk_size - 1

        self.first_chunk = (first_chunk_start, first_chunk_end)

        # Calculate request end position
        request_end = position + size - 1 if size else self.first_chunk[1]

        # Calculate last chunk range based on content position
        content_request_end = max(0, request_end - header_size)

        last_chunk_index = content_request_end // chunk_size
        last_chunk_start = header_size + (last_chunk_index * chunk_size)
        last_chunk_end = last_chunk_start + chunk_size - 1

        self.last_chunk = (last_chunk_start, last_chunk_end)

        # Calculate the chunks required to satisfy this range
        self.chunks_required = (
            (last_chunk_index or first_chunk_index) - first_chunk_index + 1
        )

        # Calculate the bytes required to satisfy this range (a request may span multiple chunks)
        self.bytes_required = self.chunks_required * chunk_size

        # Determine the slice to be used when selecting bytes from the stream data,
        # The slice should be relative to the content start within the fetched chunk data
        content_offset_in_chunk = content_position % chunk_size
        slice_left = content_offset_in_chunk
        slice_right = slice_left + size if size else chunk_size

        self.chunk_slice = slice(slice_left, slice_right, 1)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"range={self.request_range}, "
            f"size={self.size}, "
            f"first_chunk={self.first_chunk}, "
            f"last_chunk={self.last_chunk}, "
            f"chunks_required={self.chunks_required}, "
            f"bytes_required={self.bytes_required}, "
            f"chunk_slice={self.chunk_slice}, "
            f"header_size={self.header_size}, "
            f"chunk_size={self.chunk_size}"
            ")"
        )
